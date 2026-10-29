"""Vigia de descendentes vinculado à vida do controlador por um pipe privado."""

import ctypes
import os
from pathlib import Path
import selectors
import signal
import subprocess
import sys
import time


class Processo(subprocess.Popen):
    def __init__(self, argumentos, **opcoes):
        leitura, self._vida = os.pipe()
        try:
            super().__init__([sys.executable, '-I', '-B', str(Path(__file__).resolve()), str(leitura),
                              *argumentos], pass_fds=(leitura,), **opcoes)
        except BaseException:
            self._fechar_vida()
            raise
        finally:
            os.close(leitura)

    def _fechar_vida(self):
        fd, self._vida = self._vida, None
        if fd is not None:
            os.close(fd)

    def encerrar(self):
        self._fechar_vida()
        try:
            self.wait(timeout=5)
        except subprocess.TimeoutExpired:
            # Último recurso se o próprio vigia não responde.
            super().kill()
            self.wait(timeout=5)

    def communicate(self, *args, **opcoes):
        try:
            return super().communicate(*args, **opcoes)
        except BaseException:
            self.encerrar()
            raise
        finally:
            if self.returncode is not None:
                self._fechar_vida()


def limpar_descendentes():
    # O kernel mantém estes filhos vinculados ao vigia até waitpid. Não são
    # PIDs de arquivos do projeto, nem podem ser reutilizados antes da coleta.
    filhos = Path(f'/proc/self/task/{os.getpid()}/children')
    while True:
        for valor in filhos.read_text().split():
            try:
                os.kill(int(valor), signal.SIGKILL)
            except ProcessLookupError:
                pass
        try:
            while os.waitpid(-1, os.WNOHANG)[0]:
                pass
        except ChildProcessError:
            return
        time.sleep(0.01)


def vigiar(leitura, argumentos):
    libc = ctypes.CDLL(None, use_errno=True)
    # PR_SET_CHILD_SUBREAPER: recebe descendentes órfãos, inclusive os que
    # criaram outra sessão ou grupo, como GNU timeout e clientes externos.
    if libc.prctl(36, 1, 0, 0, 0) != 0:
        raise OSError(ctypes.get_errno(), 'não foi possível vigiar descendentes')
    with selectors.DefaultSelector() as seletor:
        seletor.register(leitura, selectors.EVENT_READ)
        # Se o controlador morreu antes do início do vigia, não chama o cliente.
        if seletor.select(0):
            return 137
        try:
            processo = subprocess.Popen(argumentos)
            for sinal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
                signal.signal(sinal, lambda sinal, _: processo.send_signal(sinal))
            while processo.poll() is None:
                if seletor.select(0.05):
                    # Permite a limpeza de credenciais e temporários antes de
                    # forçar a coleta dos filhos que não responderem.
                    processo.terminate()
                    try:
                        processo.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        pass
                    return 137
            return processo.returncode
        finally:
            limpar_descendentes()
            os.close(leitura)


if __name__ == '__main__':
    def interromper(*_):
        raise KeyboardInterrupt

    signal.signal(signal.SIGCHLD, signal.SIG_DFL)
    for sinal in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sinal, interromper)
    try:
        codigo = vigiar(int(sys.argv[1]), sys.argv[2:])
        raise SystemExit(codigo if codigo >= 0 else 128 - codigo)
    except KeyboardInterrupt:
        raise SystemExit(130)
    except (OSError, ValueError) as erro:
        print(f'vigia de processos: {erro}', file=sys.stderr)
        raise SystemExit(2)
