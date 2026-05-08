import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from rich.console import Console
from rich.layout import Layout
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

# Config

REGION          = os.getenv("AWS_DEFAULT_REGION", "us-west-1")
REFRESH_SECONDS = 10
CUSTOM_NS       = "CPSC454/EC2"
CPU_WARN        = 80.0
DISK_WARN       = 80.0
MEM_WARN        = 85.0
PDT             = timezone(timedelta(hours=-7))

# Cache dimension discovery results — these never change while the dashboard runs
_dim_cache: dict[str, list[dict] | None] = {}

# AWS Clients

def make_clients(region: str) -> dict:
    try:
        return {
            "ec2":     boto3.client("ec2",        region_name=region),
            "cw":      boto3.client("cloudwatch", region_name=region),
            "budgets": boto3.client("budgets",    region_name="us-east-1"),
            "sts":     boto3.client("sts"),
        }
    except NoCredentialsError:
        Console().print("[red]AWS credentials not found. Run 'aws configure' or export AWS_* env vars.[/red]")
        sys.exit(1)

def get_account_id(clients: dict) -> str:
    return clients["sts"].get_caller_identity()["Account"]

# Data Fetchers

def fetch_instances(clients: dict) -> list[dict]:
    resp = clients["ec2"].describe_instances(
        Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped", "pending"]}]
    )
    out = []
    for reservation in resp["Reservations"]:
        for inst in reservation["Instances"]:
            name = next(
                (t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), "—"
            )
            out.append({
                "id":        inst["InstanceId"],
                "name":      name,
                "type":      inst["InstanceType"],
                "state":     inst["State"]["Name"],
                "az":        inst["Placement"]["AvailabilityZone"],
                "public_ip": inst.get("PublicIpAddress", "—"),
            })
    return out


def _get_metric_stats(clients: dict, namespace: str, metric_name: str,
                      dimensions: list[dict], lookback_minutes: int = 15,
                      period: int = 60) -> float | None:
    now = datetime.now(timezone.utc)
    try:
        resp = clients["cw"].get_metric_statistics(
            Namespace=namespace,
            MetricName=metric_name,
            Dimensions=dimensions,
            StartTime=now - timedelta(minutes=lookback_minutes),
            EndTime=now,
            Period=period,
            Statistics=["Average"],
        )
        datapoints = resp.get("Datapoints", [])
        if not datapoints:
            return None
        return round(sorted(datapoints, key=lambda d: d["Timestamp"])[-1]["Average"], 2)
    except ClientError:
        return None


def _find_custom_metric_dims(clients: dict, metric_name: str, instance_id: str,
                              extra_filters: dict | None = None) -> list[dict] | None:
    """
    Discover the exact dimension set for a custom metric via list_metrics.
    Results are cached — dimensions don't change while the dashboard is running,
    and the paginator call is the single biggest latency source per refresh.
    """
    cache_key = f"{metric_name}:{instance_id}:{extra_filters}"
    if cache_key in _dim_cache:
        return _dim_cache[cache_key]

    required = {"InstanceId": instance_id}
    if extra_filters:
        required.update(extra_filters)

    result = None
    paginator = clients["cw"].get_paginator("list_metrics")
    for page in paginator.paginate(Namespace=CUSTOM_NS, MetricName=metric_name):
        for metric in page["Metrics"]:
            dims = {d["Name"]: d["Value"] for d in metric["Dimensions"]}
            if all(dims.get(k) == v for k, v in required.items()):
                result = metric["Dimensions"]
                break
        if result is not None:
            break

    _dim_cache[cache_key] = result
    return result


def fetch_cpu(clients: dict, instance_id: str) -> float | None:
    return _get_metric_stats(
        clients, "AWS/EC2", "CPUUtilization",
        [{"Name": "InstanceId", "Value": instance_id}],
        period=60,
    )


def fetch_network(clients: dict, instance_id: str) -> tuple[float | None, float | None]:
    dims = [{"Name": "InstanceId", "Value": instance_id}]
    net_in  = _get_metric_stats(clients, "AWS/EC2", "NetworkIn",  dims, period=60)
    net_out = _get_metric_stats(clients, "AWS/EC2", "NetworkOut", dims, period=60)
    return net_in, net_out


def fetch_disk(clients: dict, instance_id: str) -> float | None:
    dims = _find_custom_metric_dims(clients, "disk_used_percent", instance_id,
                                    extra_filters={"path": "/"})
    if dims is None:
        return None
    return _get_metric_stats(clients, CUSTOM_NS, "disk_used_percent", dims)


def fetch_mem(clients: dict, instance_id: str) -> float | None:
    dims = _find_custom_metric_dims(clients, "mem_used_percent", instance_id)
    if dims is None:
        return None
    return _get_metric_stats(clients, CUSTOM_NS, "mem_used_percent", dims)


def fetch_all_metrics(clients: dict, instances: list[dict]) -> dict[str, dict]:
    """Fetch all metrics for all instances in parallel."""
    metrics: dict[str, dict] = {
        inst["id"]: {"cpu": None, "disk": None, "mem": None, "net_in": None, "net_out": None}
        for inst in instances
    }
    if not instances:
        return metrics

    def _fetch(iid: str, key: str):
        if key == "cpu":
            return iid, key, fetch_cpu(clients, iid)
        if key == "disk":
            return iid, key, fetch_disk(clients, iid)
        if key == "mem":
            return iid, key, fetch_mem(clients, iid)
        return iid, key, fetch_network(clients, iid)  # key == "net"

    workers = min(32, len(instances) * 4)
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(_fetch, inst["id"], key): None
            for inst in instances
            for key in ("cpu", "disk", "mem", "net")
        }
        for fut in as_completed(futures):
            try:
                iid, key, result = fut.result()
                if key == "net":
                    metrics[iid]["net_in"], metrics[iid]["net_out"] = result
                else:
                    metrics[iid][key] = result
            except Exception:
                pass

    return metrics


def fetch_alarms(clients: dict) -> list[dict]:
    resp = clients["cw"].describe_alarms()
    return [
        {
            "name":   a["AlarmName"],
            "state":  a["StateValue"],
            "metric": a["MetricName"],
        }
        for a in resp.get("MetricAlarms", [])
    ]


def fetch_budget(clients: dict, account_id: str) -> dict | None:
    try:
        resp = clients["budgets"].describe_budgets(AccountId=account_id)
        budgets = resp.get("Budgets", [])
        if not budgets:
            return None
        b = budgets[0]
        limit  = float(b["BudgetLimit"]["Amount"])
        actual = float(
            b.get("CalculatedSpend", {})
             .get("ActualSpend", {})
             .get("Amount", 0)
        )
        pct = round((actual / limit) * 100, 1) if limit > 0 else 0
        return {"name": b["BudgetName"], "limit": limit, "actual": actual, "pct": pct}
    except ClientError:
        return None

# Helpers

def _state_color(state: str) -> str:
    return {"running": "green", "stopped": "red", "pending": "yellow"}.get(state, "white")

def _alarm_color(state: str) -> str:
    return {"OK": "green", "ALARM": "bold red", "INSUFFICIENT_DATA": "yellow"}.get(state, "white")

def _pct_color(val: float, warn: float, crit: float = 95.0) -> str:
    if val >= crit:
        return "bold red"
    if val >= warn:
        return "yellow"
    return "green"

def _fmt_bytes(b: float | None) -> str:
    if b is None:
        return "—"
    for unit in ("B", "KB", "MB", "GB"):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.1f} TB"

def _fmt_pct(val: float | None, warn: float = 80.0) -> str:
    if val is None:
        return "[dim]—[/dim]"
    color = _pct_color(val, warn)
    return f"[{color}]{val:.1f}%[/{color}]"

# Panel/Table Builders

def build_header(region: str, ts: datetime) -> Panel:
    stamp = ts.strftime("%Y-%m-%d %H:%M:%S PDT")
    text = Text.assemble(
        ("  Cloud Ops Dashboard", "bold white"),
        "   |   ",
        (f"Region: {region}", "cyan"),
        "   |   ",
        (f"Refreshed: {stamp}", "dim"),
        "   |   ",
        ("Ctrl+C to exit", "dim"),
        "  ",
    )
    return Panel(text, border_style="blue", padding=(0, 1))


def build_instances_table(instances: list[dict]) -> Table:
    t = Table(title="EC2 Instances", border_style="blue", expand=True, show_lines=False)
    t.add_column("Name",      style="cyan",  no_wrap=True)
    t.add_column("ID",        style="dim",   no_wrap=True)
    t.add_column("Type",                     no_wrap=True)
    t.add_column("State",     justify="center")
    t.add_column("AZ",        style="dim",   no_wrap=True)
    t.add_column("Public IP",                no_wrap=True)

    if not instances:
        t.add_row("—", "No instances found", "", "", "", "")
        return t

    for inst in instances:
        c = _state_color(inst["state"])
        t.add_row(
            inst["name"],
            inst["id"],
            inst["type"],
            f"[{c}]{inst['state']}[/{c}]",
            inst["az"],
            inst["public_ip"],
        )
    return t


def build_metrics_table(instances: list[dict], metrics: dict) -> Table:
    t = Table(title="Live Metrics  (refresh: 10s · CPU/Net: 1-min · Disk/Mem: 60s)", border_style="magenta",
              expand=True, show_lines=False)
    t.add_column("Instance",  style="cyan",  no_wrap=True)
    t.add_column("CPU %",     justify="right")
    t.add_column("Disk %",    justify="right")
    t.add_column("Mem %",     justify="right")
    t.add_column("Net In",    justify="right", style="cyan")
    t.add_column("Net Out",   justify="right", style="cyan")

    for inst in instances:
        m = metrics.get(inst["id"], {})
        t.add_row(
            inst["name"],
            _fmt_pct(m.get("cpu"),  CPU_WARN),
            _fmt_pct(m.get("disk"), DISK_WARN),
            _fmt_pct(m.get("mem"),  MEM_WARN),
            _fmt_bytes(m.get("net_in")),
            _fmt_bytes(m.get("net_out")),
        )
    return t


def build_alarms_table(alarms: list[dict]) -> Table:
    t = Table(title="CloudWatch Alarms", border_style="yellow", expand=True, show_lines=False)
    t.add_column("Alarm Name", style="cyan", no_wrap=True)
    t.add_column("Metric")
    t.add_column("State", justify="center")

    if not alarms:
        t.add_row("—", "No alarms configured", "—")
        return t

    for alarm in alarms:
        c = _alarm_color(alarm["state"])
        t.add_row(alarm["name"], alarm["metric"], f"[{c}]{alarm['state']}[/{c}]")
    return t


def build_budget_panel(budget: dict | None) -> Panel:
    if budget is None:
        return Panel(
            "[dim]Budget data unavailable — check IAM permissions or AWS Budgets.[/dim]",
            title="AWS Budget",
            border_style="green",
        )

    pct   = budget["pct"]
    color = "green" if pct < 80 else ("yellow" if pct < 100 else "bold red")
    filled = int(pct / 5)
    bar    = "█" * filled + "░" * (20 - filled)

    content = (
        f"  [bold]{budget['name']}[/bold]\n\n"
        f"  Spent:   [cyan]${budget['actual']:.2f}[/cyan]  /  [white]${budget['limit']:.2f} limit[/white]\n"
        f"  Usage:   [{color}]{bar}  {pct}%[/{color}]"
    )
    return Panel(content, title="AWS Budget", border_style="green")


def build_dashboard(clients: dict, account_id: str, region: str) -> Layout:
    # Fetch instances, alarms, and budget in parallel — they are all independent
    with ThreadPoolExecutor(max_workers=3) as pool:
        f_inst   = pool.submit(fetch_instances, clients)
        f_alarms = pool.submit(fetch_alarms, clients)
        f_budget = pool.submit(fetch_budget, clients, account_id)
        instances = f_inst.result()
        alarms    = f_alarms.result()
        budget    = f_budget.result()

    # Metrics need instances first, but internally parallelized per metric/instance
    metrics = fetch_all_metrics(clients, instances)
    now     = datetime.now(PDT)

    layout = Layout()
    layout.split_column(
        Layout(name="header",  size=3),
        Layout(name="middle",  ratio=2),
        Layout(name="metrics", ratio=2),
        Layout(name="budget",  size=7),
    )
    layout["middle"].split_row(
        Layout(build_instances_table(instances), name="instances", ratio=3),
        Layout(build_alarms_table(alarms),       name="alarms",    ratio=2),
    )
    layout["header"].update(build_header(region, now))
    layout["metrics"].update(build_metrics_table(instances, metrics))
    layout["budget"].update(build_budget_panel(budget))
    return layout

# Entry Point

def main():
    console = Console()
    console.print(f"\n[bold blue]Connecting to AWS ({REGION})...[/bold blue]")

    clients = make_clients(REGION)
    try:
        account_id = get_account_id(clients)
        console.print(f"[green]Authenticated. Account: {account_id}[/green]")
    except Exception as exc:
        console.print(f"[red]Authentication failed: {exc}[/red]")
        sys.exit(1)

    console.print(f"[dim]Polling every {REFRESH_SECONDS}s. Ctrl+C to exit.[/dim]\n")
    time.sleep(1)

    try:
        with Live(
            build_dashboard(clients, account_id, REGION),
            refresh_per_second=0.5,
            screen=True,
        ) as live:
            while True:
                cycle_start = time.monotonic()
                live.update(build_dashboard(clients, account_id, REGION))
                # Sleep only the time remaining so the total cycle is ~REFRESH_SECONDS,
                # regardless of how long the API calls took.
                elapsed = time.monotonic() - cycle_start
                time.sleep(max(0.0, REFRESH_SECONDS - elapsed))
    except KeyboardInterrupt:
        console.print("\n[bold blue]Dashboard closed.[/bold blue]\n")


if __name__ == "__main__":
    main()
