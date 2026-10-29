"""Travas locais de vida das reservas, sem usar PIDs do estado gravável."""

import fcntl
import os
import re
import stat


class Reservas:
    def __init__(self, pasta):
        self.pasta = pasta / 'reservas'
        self.pasta.mkdir(mode=0o700, exist_ok=True)
        if self.pasta.is_symlink():
            raise ValueError('pasta de reservas não pode ser link simbólico')
        self.diretorio = os.open(self.pasta, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC)
        self.fds = {}

    def abrir(self, dono, criar=False):
        if not isinstance(dono, str) or not re.fullmatch(r'[0-9a-f-]{36}', dono):
            raise ValueError('identificador de reserva inválido')
        fd = os.open(dono, os.O_RDWR | os.O_NOFOLLOW | os.O_CLOEXEC | os.O_NONBLOCK
                     | (os.O_CREAT if criar else 0), 0o600, dir_fd=self.diretorio)
        if not stat.S_ISREG(os.fstat(fd).st_mode):
            os.close(fd)
            raise ValueError('trava de reserva deve ser arquivo regular')
        return fd

    def segurar(self, dono):
        fd = self.abrir(dono, criar=True)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            os.close(fd)
            raise
        self.fds[dono] = fd

    def ativa(self, dono):
        if dono in self.fds:
            return True
        try:
            fd = self.abrir(dono)
        except FileNotFoundError:
            return False
        try:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return True
            return False
        finally:
            os.close(fd)

    def liberar(self, dono, remover=False):
        fd = self.fds.pop(dono, None)
        if fd is not None:
            os.close(fd)
            if remover:
                try:
                    os.unlink(dono, dir_fd=self.diretorio)
                except FileNotFoundError:
                    pass

    def fechar(self):
        for dono in tuple(self.fds):
            self.liberar(dono)
        if self.diretorio is not None:
            os.close(self.diretorio)
            self.diretorio = None
