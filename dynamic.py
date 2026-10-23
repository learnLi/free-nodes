#!/usr/bin/env python3
import re
import datetime
import requests
# import threading
from typing import Callable, List, Union, Iterable
from fetch import raw2fastly, session, LOCAL


# def kkzui():
#     # 密码在视频中口述, no use any more.
#     if LOCAL: return
#     res = session.get("https://kkzui.com/jd?orderby=modified")
#     article_url = re.search(r'<a href="(https://kkzui.com/(.*?)\.html)" title="20(.*?)节点(.*?)</a>',res.text).groups()[0]
#     res = session.get(article_url)
#     passwd = re.search(r'<strong>本期密码：(.*?)</strong>',res.text).groups()[0]
#     # print("Unlock kkzui.com with password:", passwd)
#     res = session.post(article_url, data={'secret-key': passwd})
#     sub = res.text.split('<pre')[1].split('</pre>')[0]
#     if '</' in sub:
#         sub = sub.split('</')[-2]
#     if '>' in sub:
#         sub = sub.split('>')[-1]
#     return sub

# def sharkdoor():
#     res_json = session.get(datetime.datetime.now().strftime(
#         'https://api.github.com/repos/sharkDoor/vpn-free-nodes/contents/node-list/%Y-%m?ref=master')).json()
#     res = session.get(raw2fastly(res_json[-1]['download_url']))
#     nodes: Set[str] = set()
#     for line in res.text.split('\n'):
#         if '://' in line:
#             nodes.add(line.split('|')[-2])
#     return nodes

# def changfengoss():
#     # Unused
#     res = session.get(datetime.datetime.now().strftime(
#         "https://api.github.com/repos/changfengoss/pub/contents/data/%Y_%m_%d?ref=main")).json()
#     return [_['download_url'] for _ in res]

# def vpn_fail():
#     # The site has been closed
#     # if LOCAL: return
#     response = session.get("https://vpn.fail/free-proxy/type/v2ray").text
#     lines = re.findall(r'<article(.*?)</article', response, re.DOTALL)
#     links = set()
#     ips = set()
#     for line in lines:
#         result = re.search(r'<span>(\d+)%</span>', line)
#         if result and result.group(1) == '100':
#             ips.add(re.search(r'<a href=\"https://vpn\.fail/free-proxy/ip/(.*?)\" style=', line).group(1))
#     def get_link(ip: str) -> None:
#         try:
#             response = session.get(f"https://vpn.fail/free-proxy/ip/{ip}").text
#             link = response.split('class="form-control text-center" id="pp2" value="')[1].split('"')[0]
#             links.add(link)
#         except requests.exceptions.RequestException: pass
#     threads = [threading.Thread(target=get_link, args=(ip,)) for ip in ips]
#     for thread in threads: thread.start()
#     for thread in threads: thread.join()
#     return links

# def w1770946466():
#     if LOCAL: return
#     res = session.get(raw2fastly("https://raw.githubusercontent.com/w1770946466/Auto_proxy/main/README.md")).text
#     subs: Set[str] = set()
#     for line in res.strip().split('\n'):
#         if line.startswith("`http"):
#             sub = line.strip().strip('`')
#             if not sub.startswith("https://raw.githubusercontent.com"):
#                 subs.add(sub)
#     return subs

# def fakeyou():
#     # The site has been closed
#     DOMAIN = "https://fakeyou.top"
#     res = session.get(DOMAIN)
#     res.raise_for_status()
#     url = re.search(r'<a href="(/post/\d+/)"', res.text)
#     if not url: return
#     res = session.get(DOMAIN+url.group(1))
#     lines = res.text.splitlines()
#     for line in lines:
#         line = line.strip()
#         if line.startswith("https://image.fakeyou.top/"):
#             return line.split('<')[0]+"#ignore=ss,vless"

def clashfree() -> Union[str, None]:
    """free-nodes/clashfree：每日更新的 Clash 配置，文件名带日期。

    该仓库的命名规律是 clash%Y%m%d.yml，但**某些日期的文件是 0 字节**
    （生成失败，实测 2026-10-20 / 10-21 两天为空）。sources.list 的 +date
    机制只在 HTTP 非 200 时回退日期，遇到「存在但为空」的文件会拿到空订阅
    然后直接跳过，所以这里自己回溯到最近一个非空文件。
    """
    base = "https://raw.githubusercontent.com/free-nodes/clashfree/main/clash%Y%m%d.yml"
    d = datetime.datetime.now()
    for i in range(8):
        u = (d - datetime.timedelta(days=i)).strftime(base)
        try:
            r = session.get(u, timeout=15)
        except requests.exceptions.RequestException:
            continue
        # 20 KB 起步：正常文件约 690 KB，空文件 0 字节
        if r.status_code == 200 and len(r.content) > 20000:
            return raw2fastly(u)
    return None


AUTOFUNTYPE = Callable[[], Union[str, Iterable[str], None]]
AUTOURLS: List[AUTOFUNTYPE] = []
AUTOFETCH: List[AUTOFUNTYPE] = []

AUTOURLS.append(clashfree)

if __name__ == '__main__':
    print("URL 抓取："+', '.join([_.__name__ for _ in AUTOURLS]))
    print("内容抓取："+', '.join([_.__name__ for _ in AUTOFETCH]))
    import code
    code.interact(banner='', exitmsg='', local=globals())
