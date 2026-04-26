"""
Multi-threaded Web Server (COMP2322 Project)
Supports: GET/HEAD, 5 status codes, cache, logging, persistent connections
"""

import socket
import threading
import os
import time
from datetime import datetime
from urllib.parse import unquote

# Configuration
HOST = '127.0.0.1'
PORT = 8080
WEB_ROOT = './webroot'
LOG_FILE = 'server.log'
BUFFER_SIZE = 4096


MIME_TYPES = {
    'html': 'text/html',
    'txt': 'text/plain',
    'jpg': 'image/jpeg',
    'png': 'image/png',
}


HTTP_STATUSES = {
    200: 'OK',
    304: 'Not Modified',
    400: 'Bad Request',
    403: 'Forbidden',
    404: 'Not Found',
}


log_lock = threading.Lock()

def write_log(client_ip, request_path, status_code, method='GET'):
    now = datetime.now().strftime('%d/%b/%Y %H:%M:%S')
    status_text = HTTP_STATUSES[status_code]
    log_line = f"{client_ip} [{now}] \"{method} {request_path} HTTP/1.1\" {status_code} {status_text}\n"
    with log_lock:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_line)

def get_mime_type(file_path):
    ext = file_path.split('.')[-1].lower() if '.' in file_path else ''
    return MIME_TYPES.get(ext, 'application/octet-stream')

def get_gmt_time(timestamp=None):
    if timestamp is None:
        timestamp = time.time()
    return time.strftime('%a, %d %b %Y %H:%M:%S GMT', time.gmtime(timestamp))

def is_modified_since(file_path, if_modified_since):
    try:
        file_mtime = os.path.getmtime(file_path)
        return if_modified_since != get_gmt_time(file_mtime)
    except:
        return True

def parse_http_request(data):
    try:
        lines = data.split('\r\n')
        if not lines[0]:
            return None, None, None, {}
        
        method, path, version = lines[0].split()[:3]
        method = method.upper()
        path = unquote(path)
        
        headers = {}
        for line in lines[1:]:
            if ': ' in line:
                key, value = line.split(': ', 1)
                headers[key.strip().lower()] = value.strip()
        
        if method not in ['GET', 'HEAD']:
            return None, None, version, headers
        
        if path == '/':
            path = '/index.html'
        return method, path, version, headers
    except:
        return None, None, None, {}


def create_response(status_code, headers_dict=None, body=None):
    status_text = HTTP_STATUSES[status_code]
    header = f"HTTP/1.1 {status_code} {status_text}\r\n"
    header += f"Server: MultiThreadWebServer\r\n"
    header += f"Date: {get_gmt_time()}\r\n"
    
    if headers_dict:
        for k, v in headers_dict.items():
            header += f"{k}: {v}\r\n"
    header += "\r\n"
    return header.encode('utf-8'), body if body else b''

def handle_client(conn, addr):
    client_ip = addr[0]
    try:
        while True:
            # Receive Request
            req_data = b''
            while b'\r\n\r\n' not in req_data:
                chunk = conn.recv(BUFFER_SIZE)
                if not chunk:
                    return
                req_data += chunk
            
            # Parse request
            method, path, version, headers = parse_http_request(req_data.decode('utf-8', 'ignore'))
            
            # 400 Bad Request (invalid method or malformed request)
            if not method:
                resp = create_response(400, {'Content-Type': 'text/html'}, b'<h1>400 Bad Request</h1>')
                conn.send(resp[0] + resp[1])
                write_log(client_ip, path or '/', 400)
                break
            
            # 403 Forbidden (prevent directory traversal)
            full_path = os.path.normpath(os.path.join(WEB_ROOT, path.lstrip('/')))
            if not full_path.startswith(os.path.normpath(WEB_ROOT)):
                resp = create_response(403, {'Content-Type': 'text/html'}, b'<h1>403 Forbidden</h1>')
                conn.send(resp[0] + resp[1])
                write_log(client_ip, path, 403, method)
                if headers.get('connection') == 'close': break
                continue
            
            # 404 Not Found
            if not os.path.isfile(full_path):
                resp = create_response(404, {'Content-Type': 'text/html'}, b'<h1>404 Not Found</h1>')
                conn.send(resp[0] + resp[1])
                write_log(client_ip, path, 404, method)
                if headers.get('connection') == 'close': break
                continue
            
            # 304 Not Modified
            if_modified = headers.get('if-modified-since', '')
            if if_modified and not is_modified_since(full_path, if_modified):
                mtime = get_gmt_time(os.path.getmtime(full_path))
                resp = create_response(304, {'Last-Modified': mtime})
                conn.send(resp[0])
                write_log(client_ip, path, 304, method)
                if headers.get('connection') == 'close': break
                continue
            
            # 200 OK
            with open(full_path, 'rb') as f:
                content = f.read()
            mime = get_mime_type(full_path)
            mtime = get_gmt_time(os.path.getmtime(full_path))
            conn_header = headers.get('connection', 'close')
            
            resp_headers = {
                'Content-Type': mime,
                'Content-Length': str(len(content)),
                'Last-Modified': mtime,
                'Connection': conn_header
            }
            header, _ = create_response(200, resp_headers)
            conn.send(header)
            if method == 'GET':
                conn.send(content)
            
            write_log(client_ip, path, 200, method)
            if conn_header == 'close':
                break
    finally:
        conn.close()

def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    
    print(f"Server running: http://{HOST}:{PORT}")
    print(f"Log file: {LOG_FILE}")
    try:
        while True:
            server.settimeout(1)
            try:
                conn, addr = server.accept()
            except socket.timeout:
                continue
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\nServer stopped")
    finally:
        server.close()

if __name__ == '__main__':
    main()