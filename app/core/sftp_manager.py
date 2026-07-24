"""
SFTP 文件管理器核心类

提供远程文件系统的完整操作：
- 目录浏览（列表、进入、返回上级）
- 文件操作（上传、下载、删除、重命名、新建文件夹）
- 文件信息（大小、权限、修改时间）
- 拖拽上传支持
"""
import os
import stat
import time
import re
from datetime import datetime

from PySide6.QtCore import QObject, Signal, QThread

OCTAL_ESCAPE_PATTERN = re.compile(r"\$'([^']+)'")


def _decode_octal_escape(match):
    escaped = match.group(1)
    result = []
    i = 0
    while i < len(escaped):
        if escaped[i] == '\\' and i + 1 < len(escaped):
            if escaped[i+1] in '01234567':
                octal_start = i + 1
                while octal_start < len(escaped) and escaped[octal_start] in '01234567':
                    octal_start += 1
                octal_str = escaped[i+1:octal_start]
                try:
                    result.append(chr(int(octal_str, 8)))
                except ValueError:
                    result.append(escaped[i])
                    result.append(escaped[i+1])
                i = octal_start
                continue
            elif escaped[i+1] == '\\':
                result.append('\\')
                i += 2
                continue
            elif escaped[i+1] == "'":
                result.append("'")
                i += 2
                continue
        result.append(escaped[i])
        i += 1
    return ''.join(result)


class SftpFileInfo:
    def __init__(self, name, path, file_stat=None):
        self.name = name
        self.path = path
        self.stat = file_stat
        self.size = file_stat.st_size if file_stat else 0
        self.mode = file_stat.st_mode if file_stat else 0
        self.mtime = file_stat.st_mtime if file_stat else 0

    @property
    def is_directory(self):
        return stat.S_ISDIR(self.mode) if self.mode else False

    @property
    def is_file(self):
        return stat.S_ISREG(self.mode) if self.mode else False

    @property
    def is_symlink(self):
        return stat.S_ISLNK(self.mode) if self.mode else False

    @property
    def permissions(self):
        if not self.mode:
            return "---------"
        mode = self.mode
        perms = ""
        # file type
        if stat.S_ISDIR(mode):
            perms = "d"
        elif stat.S_ISLNK(mode):
            perms = "l"
        else:
            perms = "-"
        # owner
        perms += "r" if mode & stat.S_IRUSR else "-"
        perms += "w" if mode & stat.S_IWUSR else "-"
        perms += "x" if mode & stat.S_IXUSR else "-"
        # group
        perms += "r" if mode & stat.S_IRGRP else "-"
        perms += "w" if mode & stat.S_IWGRP else "-"
        perms += "x" if mode & stat.S_IXGRP else "-"
        # other
        perms += "r" if mode & stat.S_IROTH else "-"
        perms += "w" if mode & stat.S_IWOTH else "-"
        perms += "x" if mode & stat.S_IXOTH else "-"
        return perms

    @property
    def permissions_octal(self):
        if not self.mode:
            return 0o000
        return stat.S_IMODE(self.mode)

    @property
    def size_str(self):
        if self.is_directory:
            return "-"
        size = self.size
        if size < 1024:
            return f"{size} B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.1f} KB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / (1024 * 1024):.1f} MB"
        else:
            return f"{size / (1024 * 1024 * 1024):.1f} GB"

    @property
    def modify_time(self):
        if not self.mtime:
            return ""
        try:
            return datetime.fromtimestamp(self.mtime).strftime("%Y/%m/%d %H:%M:%S")
        except Exception:
            return ""

    @property
    def type_str(self):
        if self.is_directory:
            return "文件夹"
        elif self.is_symlink:
            return "快捷方式"
        else:
            ext = os.path.splitext(self.name)[1].lower()
            common_types = {
                '.txt': '文本文件', '.md': 'Markdown', '.log': '日志',
                '.py': 'Python', '.js': 'JavaScript', '.html': 'HTML',
                '.css': 'CSS', '.json': 'JSON', '.xml': 'XML',
                '.jpg': '图片', '.png': '图片', '.gif': '图片',
                '.pdf': 'PDF', '.doc': 'Word', '.xls': 'Excel',
                '.zip': '压缩包', '.tar': '压缩包', '.gz': '压缩包',
                '.sh': '脚本', '.bat': '脚本', '.exe': '可执行文件',
                '.conf': '配置文件', '.yaml': '配置文件', '.yml': '配置文件',
            }
            return common_types.get(ext, '文件')


class SftpManager(QObject):
    file_list_updated = Signal(list)
    current_path_changed = Signal(str)
    error_occurred = Signal(str)
    transfer_progress = Signal(str, str, int, int)
    transfer_completed = Signal(str, str, bool)

    def __init__(self, sftp_client, ssh_client=None):
        super().__init__()
        self.sftp = sftp_client
        self.ssh = ssh_client  # SSH client，用于编码错误时回退
        self.current_path = '/'

    def set_sftp_client(self, sftp_client):
        self.sftp = sftp_client

    def get_current_path(self):
        return self.current_path

    def list_directory(self, path=None):
        if path is None:
            path = self.current_path
        else:
            self.current_path = path

        try:
            return self._list_by_sftp(path)
        except Exception as e:
            # SFTP 失败时，如果有 SSH client，尝试 exec_command 回退
            if self.ssh:
                try:
                    return self._list_by_ssh(path)
                except Exception as e2:
                    self.error_occurred.emit(f"列出目录失败: {str(e2)}")
                    self.current_path_changed.emit(path)
                    return []
            self.error_occurred.emit(f"列出目录失败: {str(e)}")
            self.current_path_changed.emit(path)
            return []

    def _list_by_sftp(self, path):
        files = []
        names = self.sftp.listdir(path)
        for name in names:
            if name in ('.', '..'):
                continue
            file_path = (path.rstrip('/') + '/' + name).replace('\\', '/')
            try:
                attr = self.sftp.stat(file_path)
                files.append(SftpFileInfo(name, file_path, attr))
            except Exception:
                files.append(SftpFileInfo(name, file_path, None))
        files.sort(key=lambda f: (not f.is_directory, f.name.lower()))
        self.current_path = path
        self.file_list_updated.emit(files)
        self.current_path_changed.emit(path)
        return files

    def _list_by_ssh(self, path):
        """使用 SSH exec_command 回退，解决 SFTP 编码问题"""
        files = []
        # 使用 ls -la --time-style=+%%s 获取带时间戳的列表
        cmd = f'cd "{path}" && ls -lan --time-style=+%%s 2>/dev/null || ls -lan "{path}"'
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        output = stdout.read().decode('utf-8', errors='replace')
        errs = stderr.read().decode('utf-8', errors='replace')

        if errs and not output.strip():
            raise Exception(errs.strip() or "无法获取目录列表")

        for line in output.splitlines():
            line = line.strip()
            if not line or line.startswith('total'):
                continue
            # 解析 ls -lan 输出
            parts = line.split(None, 7)
            if len(parts) < 8:
                continue
            name = parts[7]
            name = OCTAL_ESCAPE_PATTERN.sub(_decode_octal_escape, name)
            if name in ('.', '..'):
                continue

            file_path = (path.rstrip('/') + '/' + name).replace('\\', '/')

            # 解析权限
            perms_str = parts[0]
            mode = 0
            if perms_str[0] == 'd':
                mode |= stat.S_IFDIR
            elif perms_str[0] == 'l':
                mode |= stat.S_IFLNK
            else:
                mode |= stat.S_IFREG

            # rwxrwxrwx
            for i, c in enumerate(perms_str[1:], 1):
                if c == 'r':
                    if i <= 3:
                        mode |= stat.S_IRUSR
                    elif i <= 6:
                        mode |= stat.S_IRGRP
                    else:
                        mode |= stat.S_IROTH
                elif c == 'w':
                    if i <= 3:
                        mode |= stat.S_IWUSR
                    elif i <= 6:
                        mode |= stat.S_IWGRP
                    else:
                        mode |= stat.S_IWOTH
                elif c == 'x':
                    if i <= 3:
                        mode |= stat.S_IXUSR
                    elif i <= 6:
                        mode |= stat.S_IXGRP
                    else:
                        mode |= stat.S_IXOTH

            # 解析大小
            try:
                size = int(parts[4])
            except (ValueError, IndexError):
                size = 0

            # 解析时间戳
            try:
                mtime = int(parts[5])
            except (ValueError, IndexError):
                mtime = 0

            class FakeStat:
                def __init__(self, mode, size, mtime):
                    self.st_mode = mode
                    self.st_size = size
                    self.st_mtime = mtime

            fake_stat = FakeStat(mode, size, mtime)
            files.append(SftpFileInfo(name, file_path, fake_stat))

        files.sort(key=lambda f: (not f.is_directory, f.name.lower()))
        self.current_path = path
        self.file_list_updated.emit(files)
        self.current_path_changed.emit(path)
        return files

    def change_directory(self, path):
        path = path.replace('\\', '/')
        if not path.startswith('/'):
            if self.current_path.endswith('/'):
                path = self.current_path + path
            else:
                path = self.current_path + '/' + path
        path = os.path.normpath(path).replace('\\', '/')
        if not path.startswith('/'):
            path = '/' + path

        try:
            attr = self.sftp.stat(path)
            if not stat.S_ISDIR(attr.st_mode):
                self.error_occurred.emit(f"不是目录: {path}")
                return []
            self.current_path = path
            return self.list_directory(path)
        except Exception as e:
            self.error_occurred.emit(f"进入目录失败: {str(e)}")
            return []

    def go_up(self):
        if self.current_path == '/':
            return []
        parent = os.path.dirname(self.current_path).replace('\\', '/')
        if not parent:
            parent = '/'
        return self.change_directory(parent)

    def download_file(self, remote_path, local_path, callback=None):
        try:
            self.sftp.get(remote_path, local_path, callback=callback)
            return True
        except Exception as e:
            self.error_occurred.emit(f"下载失败: {str(e)}")
            return False

    def upload_file(self, local_path, remote_path, callback=None):
        try:
            self.sftp.put(local_path, remote_path, callback=callback)
            return True
        except Exception as e:
            self.error_occurred.emit(f"上传失败: {str(e)}")
            return False

    def delete_file(self, remote_path):
        try:
            info = self.sftp.stat(remote_path)
            if stat.S_ISDIR(info.st_mode):
                self._delete_directory(remote_path)
            else:
                self.sftp.remove(remote_path)
            self.list_directory()
            return True
        except Exception as e:
            self.error_occurred.emit(f"删除失败: {str(e)}")
            return False

    def _delete_directory(self, remote_path):
        try:
            names = self.sftp.listdir(remote_path)
            for name in names:
                if name in ('.', '..'):
                    continue
                fpath = (remote_path.rstrip('/') + '/' + name).replace('\\', '/')
                try:
                    attr = self.sftp.stat(fpath)
                    if stat.S_ISDIR(attr.st_mode):
                        self._delete_directory(fpath)
                    else:
                        self.sftp.remove(fpath)
                except Exception:
                    pass
            self.sftp.rmdir(remote_path)
        except Exception as e:
            self.error_occurred.emit(f"删除目录失败: {str(e)}")

    def rename_file(self, old_path, new_name):
        try:
            parent = os.path.dirname(old_path).replace('\\', '/')
            new_path = (parent.rstrip('/') + '/' + new_name).replace('\\', '/')
            self.sftp.rename(old_path, new_path)
            self.list_directory()
            return True
        except Exception as e:
            self.error_occurred.emit(f"重命名失败: {str(e)}")
            return False

    def create_directory(self, name):
        try:
            new_path = (self.current_path.rstrip('/') + '/' + name).replace('\\', '/')
            self.sftp.mkdir(new_path)
            self.list_directory()
            return True
        except Exception as e:
            self.error_occurred.emit(f"创建文件夹失败: {str(e)}")
            return False

    def get_file_stat(self, remote_path):
        try:
            stat_info = self.sftp.stat(remote_path)
            return SftpFileInfo(os.path.basename(remote_path), remote_path, stat_info)
        except Exception as e:
            self.error_occurred.emit(f"获取文件信息失败: {str(e)}")
            return None

    def get_home_directory(self):
        try:
            return self.sftp.normalize('.').replace('\\', '/')
        except Exception:
            return '/home'

    def get_parent_path(self, path):
        parent = os.path.dirname(path).replace('\\', '/')
        return parent if parent else '/'


class TransferThread(QThread):
    progress = Signal(int, int)
    completed = Signal(bool, str)

    def __init__(self, manager, transfer_type, source, destination):
        super().__init__()
        self.manager = manager
        self.transfer_type = transfer_type
        self.source = source
        self.destination = destination
        self._aborted = False

    def abort(self):
        self._aborted = True

    def _progress_callback(self, transferred, total):
        if self._aborted:
            raise Exception("传输已取消")
        self.progress.emit(transferred, total)

    def run(self):
        try:
            if self.transfer_type == 'download':
                success = self.manager.download_file(
                    self.source, self.destination,
                    callback=self._progress_callback
                )
            elif self.transfer_type == 'upload':
                success = self.manager.upload_file(
                    self.source, self.destination,
                    callback=self._progress_callback
                )
            else:
                success = False

            if success:
                self.completed.emit(True, "")
            else:
                self.completed.emit(False, "传输失败")
        except Exception as e:
            if str(e) == "传输已取消":
                self.completed.emit(False, "传输已取消")
            else:
                self.completed.emit(False, str(e))
