"""
测试 ping 解析函数在中文/英文 Windows 系统输出上的兼容性。
对应 ping_test.py 中 PingTestPage._parse_ping_output 的逻辑。
"""
import re
import sys


def parse_ping_output(output):
    """复刻 PingTestPage._parse_ping_output 的核心逻辑"""
    if not output:
        return False, 0, "无输出"
    match = re.search(r"(?:时间|time)\s*[<=]?\s*(\d+)\s*ms", output, re.IGNORECASE)
    if match:
        return True, int(match.group(1)), ""
    failure_markers = [
        "请求超时",
        "Request timed out",
        "无法访问目标主机",
        "Destination host unreachable",
        "传输失败",
        "transmit failed",
        "一般故障",
        "General failure",
        "Ping 请求找不到主机",
        "Ping request could not find host",
        "100% 丢失",
        "100% loss",
    ]
    for marker in failure_markers:
        if marker in output:
            return False, 0, marker
    return False, 0, "未知"


CASES = [
    # (描述, output, 期望 success, 期望 latency, 期望 reason 包含)
    ("英文 time=1ms", "Reply from 192.168.140.1: bytes=32 time=1ms TTL=64", True, 1, ""),
    ("英文 time<1ms", "Reply from 127.0.0.1: bytes=32 time<1ms TTL=128", True, 1, ""),
    ("英文 time=42ms", "Reply from 8.8.8.8: bytes=32 time=42ms TTL=64", True, 42, ""),
    ("英文 Request timed out", "Request timed out.", False, 0, "Request timed out"),
    ("英文 100% loss", "Packets: Sent = 1, Received = 0, Lost = 1 (100% loss),", False, 0, "100% loss"),
    ("英文 Destination unreachable",
     "Reply from 192.168.1.1: Destination host unreachable.", False, 0, "Destination"),
    ("英文 transmit failed", "PING: transmit failed, error code 65", False, 0, "transmit failed"),
    ("中文 时间=1ms", "来自 192.168.1.1 的回复: 字节=32 时间=1ms TTL=64", True, 1, ""),
    ("中文 时间<1ms", "来自 127.0.0.1 的回复: 字节=32 时间<1ms TTL=128", True, 1, ""),
    ("中文 请求超时", "请求超时。", False, 0, "请求超时"),
    ("中文 无法访问", "无法访问目标主机", False, 0, "无法访问"),
    ("中文 100% 丢失", "    数据包: 已发送 = 1, 已接收 = 0, 丢失 = 1 (100% 丢失),", False, 0, "100%"),
    ("空字符串", "", False, 0, "无输出"),
    ("无关文本", "Hello world", False, 0, "未知"),
]


def main():
    failed = 0
    for desc, output, exp_ok, exp_lat, exp_reason_part in CASES:
        ok, lat, reason = parse_ping_output(output)
        if ok != exp_ok or lat != exp_lat or exp_reason_part not in reason:
            failed += 1
            print(f"FAIL  {desc}: got (ok={ok}, lat={lat}, reason={reason!r}), "
                  f"expect (ok={exp_ok}, lat={exp_lat}, reason~={exp_reason_part!r})")
        else:
            print(f"OK    {desc}: (ok={ok}, lat={lat}, reason={reason!r})")
    print()
    if failed:
        print(f"!! {failed} / {len(CASES)} 测试失败")
        sys.exit(1)
    else:
        print(f"OK   {len(CASES)} / {len(CASES)} 测试通过")


if __name__ == "__main__":
    main()
