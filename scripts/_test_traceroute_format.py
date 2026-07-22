"""
测试路由追踪格式化输出与 IP 地理位置查询。
"""
import re


def is_private_ip(ip):
    return (
        ip.startswith('10.') or
        ip.startswith('172.16.') or ip.startswith('172.17.') or
        ip.startswith('172.18.') or ip.startswith('172.19.') or
        ip.startswith('172.20.') or ip.startswith('172.21.') or
        ip.startswith('172.22.') or ip.startswith('172.23.') or
        ip.startswith('172.24.') or ip.startswith('172.25.') or
        ip.startswith('172.26.') or ip.startswith('172.27.') or
        ip.startswith('172.28.') or ip.startswith('172.29.') or
        ip.startswith('172.30.') or ip.startswith('172.31.') or
        ip.startswith('192.168.') or
        ip.startswith('127.')
    )


def query_ip_geo(ip):
    """复刻 TraceroutePage._query_ip_geo 逻辑"""
    import requests
    try:
        url = (
            f"http://ip-api.com/json/{ip}"
            f"?fields=status,message,country,regionName,city,isp,org"
            f"&lang=zh-CN"
        )
        resp = requests.get(url, timeout=3)
        if resp.status_code == 429:
            return None, None
        data = resp.json()
        if data.get('status') == 'success':
            city = data.get('city', '')
            region = data.get('regionName', '')
            country = data.get('country', '')
            isp = data.get('isp', '') or data.get('org', '')
            location = f"{country} {region} {city}".strip()
            return location, isp
    except Exception:
        pass
    return None, None


def format_hop_line(num, times, ip, is_timeout):
    """复刻 TraceroutePage 中的格式化逻辑"""
    if is_timeout or not times:
        return f"{num:<3}  {'*':>5}  {'*':>5}  {'*':>5}  请求超时。"

    t_vals = times[:3]
    while len(t_vals) < 3:
        t_vals.append('*')

    time_strs = []
    for t in t_vals:
        if t == '*':
            time_strs.append(f"{'*':>5}")
        else:
            time_strs.append(f"{t}ms".rjust(5))

    ip_str = ip if ip else '*'
    return f"{num:<3}  {time_strs[0]}  {time_strs[1]}  {time_strs[2]}  {ip_str}"


def main():
    print("=" * 80)
    print("测试 1: 格式化输出")
    print("=" * 80)

    cases = [
        (1, ['1', '1', '1'], '192.168.140.1', False),
        (2, ['4', '5', '5'], '111.53.215.193', False),
        (3, [], None, True),
        (4, ['5'], '211.142.28.25', False),
        (5, [], None, True),
        (6, ['12', '12', '13'], '221.183.49.122', False),
        (7, ['14'], '39.156.0.46', False),
        (8, ['14', '13', '14'], '39.156.7.173', False),
        (9, [], None, True),
        (14, ['15', '14', '15'], '223.5.5.5', False),
    ]

    for num, times, ip, is_timeout in cases:
        line = format_hop_line(num, times, ip, is_timeout)
        print(line)

    print()
    print("=" * 80)
    print("测试 2: 内网 IP 过滤")
    print("=" * 80)

    test_ips = ['192.168.1.1', '10.0.0.1', '172.16.0.1', '8.8.8.8', '223.5.5.5']
    for ip in test_ips:
        print(f"  {ip:<16s} -> {'私有' if is_private_ip(ip) else '公网'}")

    print()
    print("=" * 80)
    print("测试 3: IP 地理位置查询（公网 IP）")
    print("=" * 80)

    test_public_ips = ['223.5.5.5', '8.8.8.8']
    for ip in test_public_ips:
        loc, isp = query_ip_geo(ip)
        if loc:
            print(f"  {ip}: {loc} | {isp}")
        else:
            print(f"  {ip}: 查询失败")

    print()
    print("=" * 80)
    print("测试 4: 地理位置显示去重逻辑")
    print("=" * 80)

    geo_cache = {
        '111.53.215.193': ('中国 山西 太原', 'China Mobile communications corporation'),
        '221.183.49.122': ('中国 广东 广州', 'China Mobile communications corporation'),
        '39.156.0.46': ('中国 广东 广州', 'China Mobile'),
    }

    hops = [
        {'num': 1, 'times': ['1', '1', '1'], 'ip': '192.168.140.1', 'timeout': False},
        {'num': 2, 'times': ['4', '5', '5'], 'ip': '111.53.215.193', 'timeout': False},
        {'num': 3, 'times': [], 'ip': None, 'timeout': True},
        {'num': 4, 'times': ['5'], 'ip': '211.142.28.25', 'timeout': False},
        {'num': 6, 'times': ['12', '12', '13'], 'ip': '221.183.49.122', 'timeout': False},
        {'num': 7, 'times': ['14'], 'ip': '39.156.0.46', 'timeout': False},
    ]

    last_geo_str = None
    for hop in hops:
        ip = hop['ip']
        if ip and ip in geo_cache:
            location, isp = geo_cache[ip]
            geo_str = f"  ├─ 📍 {location} | 🏢 {isp}"
            if geo_str != last_geo_str:
                print(geo_str)
                last_geo_str = geo_str
        print(format_hop_line(hop['num'], hop['times'], ip, hop['timeout']))

    print()
    print("所有测试完成")


if __name__ == "__main__":
    main()
