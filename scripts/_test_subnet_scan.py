"""
端到端测试：模拟网段Ping的实际扫描流程，验证 _parse_ping_output
在真实 ping 命令输出下的中英文兼容性。
"""
import sys
import subprocess
import re
import time
from concurrent.futures import ThreadPoolExecutor, as_completed


def parse_ping_output(output):
    """PingTestPage._parse_ping_output 的内联复刻"""
    if not output:
        return False, 0, "无输出"
    match = re.search(r"(?:时间|time)\s*[<=]?\s*(\d+)\s*ms", output, re.IGNORECASE)
    if match:
        return True, int(match.group(1)), ""
    failure_markers = [
        "请求超时", "Request timed out",
        "无法访问目标主机", "Destination host unreachable",
        "传输失败", "transmit failed",
        "一般故障", "General failure",
        "Ping 请求找不到主机", "Ping request could not find host",
        "100% 丢失", "100% loss",
    ]
    for marker in failure_markers:
        if marker in output:
            return False, 0, marker
    return False, 0, "未知"


def scan_host(host, timeout_s=1, size=32):
    """复刻 run_subnet_ping 内嵌的 scan_host 闭包"""
    try:
        last_num = int(host.split(".")[-1])
    except Exception:
        return None, None, None
    try:
        cmd = f"ping -n 1 -w {timeout_s * 1000} -l {size} {host}"
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s + 2)
        success, _, _ = parse_ping_output(result.stdout)
        return host, last_num, success
    except Exception:
        return host, last_num, False


def main():
    # 构造一个 192.168.140.0/30 的极小网段用于快速验证
    # .1 (本机路由器)  .2 (网关)  .0/3 (网络/广播)
    base = "192.168.140"
    hosts = [f"{base}.{i}" for i in range(1, 11)]  # 1~10：包含至少1个本机/路由器，其他大多离线

    print(f"扫描 {base}.0/28 中的 10 个 IP: {hosts}")
    print()

    online = 0
    offline = 0
    started = time.time()
    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = [ex.submit(scan_host, h) for h in hosts]
        for fut in as_completed(futures):
            host, last_num, success = fut.result()
            if last_num is None:
                continue
            if success:
                online += 1
                print(f"  {host:>15s}  在线")
            else:
                offline += 1
                print(f"  {host:>15s}  离线")
    elapsed = time.time() - started
    total = online + offline
    rate = (online / total * 100) if total > 0 else 0
    print()
    print(f"结果: 在线 {online} / 离线 {offline} / 总 {total} / 在线率 {rate:.1f}% (耗时 {elapsed:.1f}s)")

    # 关键断言：在线数 >= 1（说明英文系统也能正确识别 time=1ms 成功）
    if online < 1:
        print("FAIL: 应当至少识别出 1 个在线主机（路由器或本机）")
        sys.exit(1)
    print("OK: 至少识别出 1 个在线主机，英文系统兼容通过")


if __name__ == "__main__":
    main()
