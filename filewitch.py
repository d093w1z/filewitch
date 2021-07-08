import http.server
import os
import re
import shutil
import socket
import socketserver
import urllib
import sys
from io import BytesIO
from zipfile import ZipFile

import qrcode
import qrcode.image.svg

import traceback

try:
    import lxml.etree as ET
except ImportError:
    import xml.etree.ElementTree as ET
import mimetypes

mimetypes.init()

PORT = 8010
PATH = "data"
home = os.path.expanduser("~")
qr = None
PROJPATH = None


class RequestHandler(http.server.BaseHTTPRequestHandler):
    output_dir = PATH
    absolute_path = os.path.abspath("./template")

    home = os.path.expanduser("~")
    nice_path = absolute_path.replace(home, "~")
    _output_dir = output_dir
    prev_dir = output_dir
    curr_dir = output_dir
    all_files = []
    all_subdirs = []
    link = None

    def do_HEAD(self):
        f = self.send_default()
        if f:
            f.close()

    def do_GET(self):
        f = BytesIO()
        response_code = 200
        content_type = "text/html; charset=utf-8"
        request_path = self.path.split("?")
        request_url = ""
        request_opt = {}
        if request_path:
            request_url = request_path[0]
        if len(request_path) > 1:
            for pair in request_path[1].split("&"):
                if pair:
                    opt, value = pair.split("=")
                    request_opt[opt] = value
            print(request_opt)
        try:
            if request_url == "/"  and "path" not in request_opt.keys() and len(request_opt.keys())==0:
                self._output_dir = PATH
                f = self.send_default()

            elif request_url and len(request_opt.keys())==0:
                filepath = os.path.join(self.absolute_path, os.path.join(*request_url.split("/")))
                print("Requested filepath: ", filepath, request_url)
                type_guess, encoding = mimetypes.guess_type(filepath)
                f = open(filepath, "rb")
                content_type = type_guess
                if encoding:
                    content_type += "; " + encoding

            elif "path" in request_opt.keys():
                if not request_opt["path"]:
                    raise FileNotFoundError
                request_path_formatted = urllib.parse.unquote(request_opt["path"].split("./")[-1]).split("/")
                filepath = os.path.join(PROJPATH, *request_path_formatted)
                print("Requested filepath with path: ", filepath, request_opt)
                type_guess, encoding = mimetypes.guess_type(filepath)
                f = open(filepath, "rb")
                content_type = type_guess
                if encoding:
                    content_type += "; " + encoding

            elif len(request_opt.keys()) > 0:
                zip = ZipFile(os.path.join(PROJPATH,self.output_dir,"download.zip"),"w")
                for name in request_opt.keys():
                    request_path_formatted = urllib.parse.unquote(name.split("./")[-1]).split("/")
                    filename_with_path = os.path.join(PROJPATH, *request_path_formatted)
                    zip.write(filename_with_path, os.path.basename(filename_with_path))
                zip.close()
                filepath = os.path.join(PROJPATH,self.output_dir, "download.zip")
                print("Requested filepath NEW version: ", filepath, request_url)
                type_guess, encoding = mimetypes.guess_type(filepath)
                f = open(filepath, "rb")
                content_type = type_guess
                if encoding:
                    content_type += "; " + encoding


        except FileNotFoundError as e:
            print("ERROR: File not found:", os.path.join(self.output_dir, request_url), "requested by ",
                  self.client_address, "not found.")
            # traceback.print_exc()
            f = BytesIO()
            file = open("file-not-found.html", "rb")
            qrsvg = re.sub(b"fill:#000000;", b"", qr.qr_getstring())
            contents = file.read()
            contents = re.sub(b"#####QRCODE#####", qrsvg, contents)
            contents = re.sub(b"#####LINK#####", get_link().encode(), contents)

            file.close()
            f.write(contents)
            response_code = 404
        except (IsADirectoryError, PermissionError) as e:
            if request_url and "path" not in request_opt.keys():
                dirpath = os.path.join(self.output_dir, request_url)
                self._output_dir = request_url
            else:
                dirpath = request_opt["path"]
                self.prev_dir = os.path.split(dirpath)[0]
                self._output_dir = dirpath
                # print(dirpath, self.curr_dir, self.prev_dir, self.output_dir, self._output_dir, request_opt["path"])
            print(e,"WARN: Directory request:", dirpath, "requested by ", self.client_address)
            f = self.send_default()
        f.read()
        length = f.tell()
        f.seek(0)
        self.send_response(response_code)
        self.send_header("Content-type", content_type)
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    def do_POST(self):
        """Serve a POST request."""
        result, info = self.deal_post_data()
        if "\\" in info:
            info = "\\\\".join(info.split("\\"))
        status = b"Success: " if result else b"Failed: "
        info = ("<span>%s</span><br><br><a href=\"%s\">back</a>" % (info, self.headers['referer'])).encode()

        f = BytesIO()
        file = open("upload-status.html", "rb")
        qrsvg = re.sub(b"fill:#000000;", b"", qr.qr_getstring())
        contents = file.read()
        contents = re.sub(b"#####STATUS#####", status, contents)
        contents = re.sub(b"#####INFO#####", info, contents)
        contents = re.sub(b"#####QRCODE#####", qrsvg, contents)
        contents = re.sub(b"#####LINK#####", get_link().encode(), contents)

        file.close()
        f.write(contents)

        length = f.tell()
        f.seek(0)
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(length))
        self.end_headers()
        if f:
            self.copyfile(f, self.wfile)
            f.close()

    def log_message(self, format, *args):
        pass

    # if self._debug:
    # super().log_message(format, *args)

    def deal_post_data(self):
        uploaded_files = []
        content_type = self.headers['content-type']
        if not content_type:
            return (False, "Content-Type boundary not specified")
        # Get the boundary for splitting files
        boundary = content_type.split("=")[1].encode()
        remainbytes = int(self.headers['content-length'])
        # Read first line, it should be boundary
        line = self.rfile.readline()
        remainbytes -= len(line)

        if boundary not in line:
            return (False, "Content does not begin with boundary")
        while remainbytes > 0:
            line = self.rfile.readline()
            remainbytes -= len(line)
            fn = re.findall(r'Content-Disposition.*name="files\[\]"; filename="(.*)"',
                            line.decode("utf-8", "backslashreplace"))
            if not fn:
                return (False, "Filename not found")
            file_name = fn[0]
            fn = os.path.join(PROJPATH,self._output_dir, file_name)
            # Skip Content-Type
            line = self.rfile.readline()
            remainbytes -= len(line)
            # Skip \r\n
            line = self.rfile.readline()
            remainbytes -= len(line)
            try:
                out = open(fn, 'wb')
            except IOError:
                print(fn)
                return (False, "File write failed, do you have permission to write?")
            else:
                with out:
                    preline = self.rfile.readline()
                    remainbytes -= len(preline)
                    while remainbytes > 0:
                        line = self.rfile.readline()
                        remainbytes -= len(line)
                        if boundary in line:
                            # Meets boundary, this file finished. We remove \r\n because of \r\n is introduced by protocol
                            preline = preline[0:-1]
                            if preline.endswith(b'\r'):
                                preline = preline[0:-1]
                            out.write(preline)
                            uploaded_files.append(os.path.join(self.nice_path, file_name))
                            break
                        else:
                            # If not boundary, write it to output file directly.
                            out.write(preline)
                            preline = line
        return (True, "File '%s' upload success!" % ",".join(uploaded_files))

    def send_default(self):
        f = BytesIO()
        file_index = open("index.html", "rb")
        if self.link != get_link():
            self.link = get_link()
            qr.qr_generate(self.link)
        print(os.getcwd())
        self.all_subdirs = [dir for dir in os.listdir(os.path.join(PROJPATH,self._output_dir)) if
                            os.path.isdir(os.path.join(PROJPATH,self._output_dir, dir))]
        self.all_files = [file for file in os.listdir(os.path.join(PROJPATH,self._output_dir)) if
                          not os.path.isdir(os.path.join(PROJPATH,self._output_dir, file))]
        dirlisting = "<ul>"
        dirlisting += "<li><a href=\"?path=%s\">..</a></li>" % (self.prev_dir)
        for dir in self.all_subdirs:
            dirlisting += "<a href=\"?path=%s\"><li><b>%s</b></li></a>" % ("/".join([self._output_dir, dir]), dir)
        dirlisting += "</ul>"
        filelisting = "<ul>"
        for file in self.all_files:
            filelisting += "<p><input type=\"checkbox\" class=\"file-check\" name=\"%s\" /><a href=\"?path=%s\" download=\"%s\">%s</a></p>"
            filelisting = filelisting % (
            "/".join([self._output_dir, file]),  "/".join([self._output_dir, file]), file, file)
        dirlisting = dirlisting.encode()
        filelisting = filelisting.encode()
        contents = file_index.read()
        qrsvg = re.sub(b"fill:#000000;", b"", qr.qr_getstring())
        contents = re.sub(b"#####DIRLIST#####", dirlisting, contents)
        contents = re.sub(b"#####FILELIST#####", filelisting, contents)
        contents = re.sub(b"#####QRCODE#####", qrsvg, contents)
        contents = re.sub(b"#####LINK#####", get_link().encode(), contents)

        file_index.close()
        f.write(contents)
        # displaypath = html.escape(urllib.parse.unquote(self.nice_path))
        return f

    def copyfile(self, source, outputfile):
        shutil.copyfileobj(source, outputfile)





def get_link():
    global PORT
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.connect(("8.8.8.8", 80))
    link = "http://" + s.getsockname()[0] + ":" + str(PORT)
    return link


class QRHandler:
    tmp_qr = None

    def __init__(self, _link):

        Handler = RequestHandler
        self.qr_generate(_link)

    def qr_generate(self, link):
        self.tmp_qr = qrcode.QRCode(version=1,
                                error_correction=qrcode.constants.ERROR_CORRECT_L,
                                border=4,
                                box_size=10)
        self.tmp_qr.add_data(link)
        self.tmp_qr.make(fit=True)
        # return self.qr

    def qr_print(self):
        # self.qr.print_tty()
        self.tmp_qr.print_ascii()

    def qr_getstring(self):
        img = self.tmp_qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
        img.save("qr-link.svg")
        svg = img.get_image()
        qrstring = "".join(ET.tostring(svg).decode().split("\\n")).encode()
        return qrstring

def main():
    global PATH, qr, PROJPATH
    if len(sys.argv) == 2:

        tmp = sys.argv[1]
        if ".." not in tmp:
            PATH = tmp

    if PATH not in os.listdir():
        os.mkdir(PATH)
    PROJPATH = os.getcwd()
    os.chdir("template")

    Handler = RequestHandler
    try:
        with socketserver.TCPServer(("", PORT), Handler) as httpd:
            print("Serving at port :", PORT)
            print("Directory :", PATH)
            print("Type this in Browser", get_link())
            print("or Use the following QRCode")
            qr = QRHandler(get_link())
            qr.qr_print()
            httpd.serve_forever()
    except Exception as e:
        print(e)
    except KeyboardInterrupt:
        print("KeyboardInterrupt recieved, Exiting.")
        pass
# main()
if __name__ == "__main__":
    main()
