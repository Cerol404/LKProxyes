import os
import requests
from bs4 import BeautifulSoup
import concurrent.futures
import time
import socket
from fake_useragent import UserAgent
import random
import sys

# Configurações
PROXY_SOURCES = [
    'https://www.socks-proxy.net/',
    'https://free-proxy-list.net/',
    'https://www.proxy-list.download/SOCKS4',
    'https://www.proxy-list.download/SOCKS5',
    'https://spys.one/en/socks-proxy-list/',
    'https://proxyscrape.com/free-proxy-list',
    'https://www.freeproxy.world/?type=socks4',
    'https://www.freeproxy.world/?type=socks5'
]
TEST_URL = 'http://example.com'
TIMEOUT = 30
MAX_PROXIES = 50
PROXYCHAINS_CONF = '/etc/proxychains4.conf'

headers = {'User-Agent': UserAgent().random}

def get_proxies():
    proxies = []
    for url in PROXY_SOURCES:
        try:
            res = requests.get(url, headers=headers, timeout=TIMEOUT)
            soup = BeautifulSoup(res.text, 'html.parser')
            
            for table in soup.find_all('table'):
                for row in table.find_all('tr'):
                    cols = row.find_all(['td', 'th'])
                    if len(cols) >= 2:
                        ip = cols[0].text.strip().split(' ')[0]
                        port = cols[1].text.strip().split(' ')[0]
                        
                        # Verifica protocolo SOCKS4 ou SOCKS5
                        protocol_col = cols[4].text.strip().lower() if len(cols) > 4 else ''
                        if 'socks4' in protocol_col:
                            proxies.append((f"{ip}:{port}", 'socks4'))
                        elif 'socks5' in protocol_col:
                            proxies.append((f"{ip}:{port}", 'socks5'))
        except Exception as e:
            print(f"Erro em {url}: {str(e)[:50]}")
    return list(set(proxies))

def test_proxy(proxy):
    proxy_addr, proxy_type = proxy
    try:
        ip, port = proxy_addr.split(':')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(TIMEOUT)
        start_time = time.time()
        
        # Teste de conexão TCP
        if sock.connect_ex((ip, int(port))) != 0:
            return None
        
        if proxy_type == 'socks4':
            # Handshake SOCKS4
            sock.sendall(
                b'\x04\x01' + 
                int(port).to_bytes(2, 'big') + 
                socket.inet_aton(ip) + 
                b'\x00'
            )
            
            response = sock.recv(8)
            if len(response) != 8 or response[1] != 0x5a:  # 0x5a = sucesso
                return None
        elif proxy_type == 'socks5':
            # Handshake SOCKS5
            sock.sendall(b'\x05\x01\x00')
            response = sock.recv(2)
            if len(response) != 2 or response[1] != 0x00:  # 0x00 = sucesso
                return None
            
            # Envia requisição de conexão
            sock.sendall(
                b'\x05\x01\x00\x01' + 
                socket.inet_aton(ip) + 
                int(port).to_bytes(2, 'big')
            )
            response = sock.recv(10)
        
            if len(response) < 2 or response[1] != 0x00:  # 0x00 = sucesso
                return None
        
        # Teste de requisição HTTP
        proxies = {
            'http': f'{proxy_type}://{proxy_addr}',
            'https': f'{proxy_type}://{proxy_addr}'
        }
        
        res = requests.get(
            TEST_URL,
            proxies=proxies,
            timeout=TIMEOUT,
            headers=headers
        )
        
        if res.status_code == 200:
            return (proxy_addr, proxy_type, time.time() - start_time)
        
    except Exception as e:
        pass
    finally:
        sock.close()
    return None

def get_existing_proxies():
    """Lê os proxies existentes no arquivo proxychains.conf."""
    existing_proxies = []
    try:
        with open(PROXYCHAINS_CONF, 'r') as f:
            lines = f.readlines()
        
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('socks4') or stripped.startswith('socks5'):
                parts = stripped.split()
                if len(parts) == 3 and (parts[0] == 'socks4' or parts[0] == 'socks5'):
                    existing_proxies.append((f"{parts[1]}:{parts[2]}", parts[0]))
    except Exception as e:
        print(f"Erro ao ler proxies existentes: {e}")
    return existing_proxies

def clean_existing_proxies():
    """Testa os proxies existentes e remove os que não funcionam."""
    existing_proxies = get_existing_proxies()
    working_proxies = []
    
    if not existing_proxies:
        print("⚠️ Nenhum proxy existente encontrado no arquivo proxychains.conf.")
        return []
    
    print(f"🔍 Testando {len(existing_proxies)} proxies existentes...")
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(test_proxy, existing_proxies)
        
        for result in results:
            if result:
                proxy_addr, proxy_type, latency = result
                print(f"✅ Proxy existente funcional: {proxy_type}://{proxy_addr} | Latência: {latency:.2f}s")
                working_proxies.append((proxy_addr, proxy_type))
            else:
                print(f"❌ Proxy existente falhou.")
    
    return working_proxies

def update_proxychains(new_proxies):
    try:
        if not os.access(PROXYCHAINS_CONF, os.W_OK):
            print("⚠️ Execute com sudo para atualizar o proxychains")
            return
        
        with open(PROXYCHAINS_CONF, 'r') as f:
            config = f.read()
        
        # Remove proxies antigos
        header, _, _ = config.partition('[ProxyList]')
        new_config = f"{header.strip()}\n[ProxyList]\n"
        
        # Adiciona novos proxies no formato socks4 ou socks5
        for proxy in new_proxies[:MAX_PROXIES]:
            proxy_addr, proxy_type = proxy
            ip, port = proxy_addr.split(':')
            new_config += f"{proxy_type} {ip} {port}\n"
        
        with open(PROXYCHAINS_CONF, 'w') as f:
            f.write(new_config)
        
        print(f"✅ Proxychains atualizado com {len(new_proxies[:MAX_PROXIES])} proxies ({proxy_type})")
        
    except Exception as e:
        print(f"❌ Erro: {e}")

spinners = [
"⣾",
"⣷",
"⣯",
"⣟",
"⡿",
"⡱",
"⡇",
"⡧",
]

def main():
    print(fr"""

 ░▒▓██████▓▒░░▒▓████████▓▒░▒▓███████▓▒░ ░▒▓██████▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░ 
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░ 
░▒▓█▓▒░      ░▒▓██████▓▒░ ░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░ 
░▒▓█▓▒░      ░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░      ░▒▓█▓▒░ 
░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░      ░▒▓█▓▒░ 
 ░▒▓██████▓▒░░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░░▒▓██████▓▒░░▒▓████████▓▒░▒▓█▓▒░▒▓████████▓▒░      ░▒▓█▓▒░ 

   ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⣴⣶⣄⠀⠐⣶⣶⣶⣶⣶⡖⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣴⣶⣶⠆⠀⠀⢀
⠀⠀⠀   ⠀⠀⠀⠀⠀⠀⠀⠀⠈⢻⡏⢅⠄⡀⠉⢛⡙⠙⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠠⢄⡆⡀⠀⢀⣠⣤⣾⣿⣿⣿⡃⠀⠀⢸
   ⠀⡀⠀⠀⠂⠀⠀⠀⠈⢀⠀⠀⢠⣷⡏⣲⡀⣀⠀⠀⠀⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢀⡐⠌⣘⣲⡄⣿⣿⣿⣿⣿⣿⣿⡅⠀⠀⠀
   ⣿⢕⠀⠀⠀⠀⠀⠐⠀⠋⠀⠀⢸⡟⡜⢣⣹⣿⣿⣶⣶⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡚⠃⠀⠉⢿⡧⠘⠉⠁⠈⢻⢿⣿⠆⠀⠀⠀
   ⡵⡾⠀⠀⠀⠀⠿⠛⠁⠀⠀⠀⠈⠀⠀⣤⣶⣶⣶⣶⣤⣀⢠⠀⠀⡀⢀⠀⡀⠀⢤⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢠⢀⣀⣠⣾⣇⠀⠀⠀⠀⠀⠈⠹⡃⠀⠀⠀
   ⣦⠁⠀⠀⢘⣦⡀⠀⠤⠒⠈⠀⠀⠀⠀⠀⢠⡀⣄⡀⣀⠀⠀⠈⠀⠉⠈⠘⠒⠛⠂⠀⠀⠀⠀⠴⣤⢢⣄⠀⠀⣄⣀⠘⠻⢿⡗⠀⠀⠀⠀⠀⠀⠀⡅⠀⠀⠀
   ⣟⣧⠀⠀⠼⠛⣥⡃⠄⡀⠀⠀⠀⠀⠀⠀⣮⣽⣿⣿⣿⣻⡖⣶⣼⣦⣴⣀⢀⠀⢠⠠⠄⡀⢀⠀⠀⠀⠀⠈⠉⠈⠀⠙⠀⠄⠈⠀⠀⠀⢀⣴⣶⣶⠆⠀⠀⠀
   ⣿⣿⡀⠀⠀⠀⣿⡹⢎⠔⠀⡀⠀⠀⠀⠴⠺⣿⣿⣿⠃⠁⠈⠈⠉⠛⠻⡹⣞⡂⢅⡊⠴⡐⢏⡟⣼⣿⣿⢦⣦⠀⠀⠀⠀⠀⠀⠀⠀⣠⣿⢸⣿⣿⡃⠀⠀⠀
   ⣿⣿⡆⢰⣤⡀⠙⡸⢌⡚⠄⠀⠀⠀⠀⣠⣿⣿⣿⠅⠀⠀⠀⠀⠀⠀⠀⠘⢆⠱⠀⠨⠑⠉⠀⠀⠀⠀⠀⠉⣾⠀⠀⠀⠀⠀⢰⣠⣶⣷⣾⡟⣿⣿⠇⠀⠀⠈
   ⣿⣿⡇⠫⣿⣿⠀⠀⠃⠜⡄⠀⠀⠀⠀⣽⣿⣿⠏⠃⠀⠀⠀⠀⠀⠀⠀⡀⡈⣔⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⣼⡄⠀⠀⠀⠀⠈⣿⣿⣿⣿⣿⣻⣿⡇⠀⠀⠀
   ⣿⣿⣀⣤⣿⣿⣇⠀⠀⢰⡀⠀⠈⠄⠀⣿⣿⣿⠦⣁⠒⣶⣴⣴⡶⢼⢭⣇⠞⠁⠀⠘⡤⣀⠀⠀⠀⠀⠀⢦⣹⡇⠀⠀⠀⡜⠀⣿⡿⠛⣵⣿⣿⣿⡆⠀⠀⠀
   ⣿⣿⣿⣅⠀⠚⣿⡆⠀⠢⠄⠀⠀⢂⠀⣿⣿⣿⢰⢩⡙⣾⣿⣿⢯⣯⣿⠇⠀⠀⠀⠀⢰⢩⣿⠇⠀⣀⠉⠢⢵⡇⠀⠀⡘⠄⠐⠋⣠⣾⣿⣿⣿⣿⠆⠀⠀⠀
   ⣿⣿⣿⣿⣧⣠⣼⣿⠀⢀⠂⠀⠀⠀⢂⠙⢍⠣⣋⢧⣝⣾⣿⣿⣿⣿⡏⠀⠀⠀⠀⠀⢨⣹⢎⠀⢦⠑⢢⡙⡼⠀⠀⡐⠀⠀⢀⣼⣿⣿⣿⣿⣿⣿⡇⠀⠀⢈
   ⣿⣿⣿⣿⣿⣿⣧⠥⢭⣤⣤⠀⠀⠀⠢⠀⠀⠀⠀⠜⣿⣿⣿⡏⣿⣿⠟⣀⠠⢢⠄⡀⢤⣛⡎⠜⠢⠉⠂⠁⠀⠀⠐⠀⠀⡀⣿⣿⣿⣿⣿⣿⣿⣿⡷⡇⠀⠀
   ⣿⣿⣿⣿⣿⣿⢱⢃⠀⠉⠃⠀⠀⠀⠀⡃⠀⠀⠀⠀⠾⣿⣿⢱⡧⡇⠀⡣⠘⡁⠂⠴⢸⣟⠀⡀⠀⠀⠀⠀⠀⠀⠀⠀⠘⣱⣿⣿⣿⣿⣿⣿⣿⣿⡇⠄⠀⠀
   ⣿⣿⣿⣿⣿⣿⣎⢧⠂⠀⠀⠀⠀⠀⠀⠰⠁⠀⠀⠀⠀⣯⢋⡎⡑⣁⢐⡑⣀⠃⡘⠠⣻⠍⠀⠀⠀⠀⢠⣶⣶⡖⠀⣀⣤⣛⠻⣿⣿⣿⣿⣿⣿⣿⠆⠀⠀⠀
   ⣿⣿⣿⣿⣿⣿⣿⣯⡣⡅⡀⠀⠀⠱⣀⠀⠑⠀⠀⠀⠀⠀⡇⢨⠀⠃⠈⠃⠘⠐⠂⠂⠒⠀⠀⠀⠀⠀⠀⢻⣿⠀⢼⣿⣿⣿⣿⣦⡙⢿⣿⣿⣿⣿⡃⠀⠀⢀
   ⠙⣿⠿⡿⢿⣿⣿⣿⣷⣜⠡⣆⡀⠀⠀⠈⠄⠠⠀⠀⠀⠀⡏⡔⠰⠀⠆⡄⢀⠀⡘⠐⠀⠀⠀⠀⠀⠀⠠⣌⢿⠀⣼⣿⣿⣿⣿⣿⠿⢸⣿⣿⣿⣿⠄⠀⠀⠀
  ⠀⠀⠀⠃⢫⣿⣿⣿⣿⣿⣷⠆⠹⢤⡀⠀⠀⠀⠈⠀⠃⠄⠀⠁⠀⠘⠀⠀⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠐⠌⠎⢀⣿⣿⣿⣿⠟⣡⣾⣿⣿⣿⣿⣿⠂⠀⠀⠀
  ⠀⠀⠀⠀⠀⠈⠙⠿⢿⣿⣿⣾⢁⠀⠉⠣⠄⠀⠀⠀⠀⠆⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⣿⣿⡿⠛⠰⠿⠁⠀⠉⢹⣿⣿⠁⠀⠀⠀
  ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠫⣭⣓⠏⠤⢠⡊⠑⣠⡀⠀⠀⠀⠁⠀⠰⠀⠀⢀⠀⠀⠀⠀⠀⠀⠀⠂⠄⠀⠀⠀⠀⠉⠋⠁⠀⠀⠀⠀⠀⠀⠈⢟⡿⠀⠀⠀⠀
  ⠀ ⠀⠀⠀⠀⠀⠀⠐⡠⠀⠀⠈⠛⢿⣶⣬⡖⠁⠄⠳⠆⣀⠀⠀⠀⠀⠀⠀⠈⠀⠀⡐⠀⠡⠀⠀⠀⠠⠀⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⡞⠀⠀⠀⠐
   ⠀⠀⠀⠀⠀⠀⠀⠀⡑⠬⢠⠀⠀⠀⠈⠀⠏⠀⠈⢀⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠄⠀⠀⠀⠀⠀⠁⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢘⠀⠀⠀⠈
   ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⡁⠎⠤⡀⠀⠀⠀⠀⠀⠀⠂⠈⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠀
   ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⢐⢢⢒⡡⣀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
   ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠈⠀⠀⠀⠡⠚⡐⠂⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
⠀   ⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠁⠀⠀⠡⠀⠁⠀⠠⠁⠀⠄⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀⠀
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓███████▓▒░░▒▓███████▓▒░ ░▒▓██████▓▒░░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓████████▓▒░ 
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░        
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░        
░▒▓█▓▒░      ░▒▓███████▓▒░░▒▓███████▓▒░░▒▓███████▓▒░░▒▓█▓▒░░▒▓█▓▒░░▒▓██████▓▒░ ░▒▓██████▓▒░░▒▓██████▓▒░   
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓█▓▒░        
░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓█▓▒░        
░▒▓████████▓▒░▒▓█▓▒░░▒▓█▓▒░▒▓█▓▒░      ░▒▓█▓▒░░▒▓█▓▒░░▒▓██████▓▒░░▒▓█▓▒░░▒▓█▓▒░  ░▒▓█▓▒░   ░▒▓████████▓▒░ 
                                                                                                          
                                                                                                                                                                                                              
 """)

    for i in range(1, 101):
        spinner = random.choice(spinners)
        progress = "#" * (i // 2)
        sys.stdout.write(f"\r\033[92mCarregando...\033[0m [ {progress} ] {i}%")
        sys.stdout.flush()
        time.sleep(0.01) 

    time.sleep(1)
    os.system('cls' if os.name == 'nt' else 'clear')

    # Passo 1: Limpar proxies existentes
    working_existing_proxies = clean_existing_proxies()
    
    # Passo 2: Obter novos proxies
    print("\n🔍 Buscando novos proxies SOCKS4 e SOCKS5...")
    new_proxies = get_proxies()
    print(f"🌐 {len(new_proxies)} novos proxies encontrados. Testando...\n")
    
    working_new_proxies = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as executor:
        results = executor.map(test_proxy, new_proxies)
        
        for result in results:
            if result:
                proxy_addr, proxy_type, latency = result
                print(f"✅ Funcional: {proxy_type}://{proxy_addr} | Latência: {latency:.2f}s")
                working_new_proxies.append((proxy_addr, proxy_type))
            else:
                print(f"❌ Um proxy falhou.")
    
    # Combina proxies com os proxies que já existem
    all_working_proxies = working_existing_proxies + working_new_proxies
    all_working_proxies = list(set(all_working_proxies))  # Remove os duplicados
    
    if all_working_proxies:
        print(f"\n🚀 Melhores proxies:")
        for proxy in all_working_proxies[:MAX_PROXIES]:
            proxy_addr, proxy_type = proxy
            print(f"- {proxy_type}://{proxy_addr}")
        update_proxychains(all_working_proxies)
    else:
        print("\n❌ Nenhum proxy funcional encontrado")

if __name__ == '__main__':
    main()
