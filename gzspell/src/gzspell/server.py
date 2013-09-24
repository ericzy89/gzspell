"""
Start a backend server.

The server opens an INET socket locally at a given port (defaults to
9000).

Messages sent to and from the server are wrapped as follows:  First byte
indicates the number of following bytes (NOT characters), up to 255.
Messages are encoded in UTF-8.  See wrap().

Commands sent to the server have the format: "COMMAND arguments"

The server recognizes the following commands:

CHECK word
    Checks the given word and returns:

    - OK
    - ERROR

CORRECT word
    Calculates the best correction for the given word and returns it.

PROCESS word
    Checks and corrects if not correct:

    - OK
    - WRONG suggestion

Socket is closed after each transaction.

"""

import logging
import argparse
import socket
import atexit
import shlex

from gzspell import analysis

logger = logging.getLogger(__name__)


def main(*args):

    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=9000)
    parser.add_argument('--host', default='localhost')
    parser.add_argument('--db', default='lexicon')
    parser.add_argument('--user', default='lexicon')
    parser.add_argument('--pw', default='')
    args = parser.parse_args(args)

    spell = analysis.Spell(
        analysis.DB(host=args.host, db=args.db, user=args.user))

    # commands
    cmd_dict = {
        "CHECK": spell.check,
        "CORRECT": spell.correct,
        "PROCESS": spell.process,
    }

    # open socket
    sock = socket.socket(socket.AF_INET)
    addr = ('', args.port)
    sock.bind(addr)
    atexit.register(_close, sock)
    sock.listen(5)
    logger.debug("Socket bound and listening to %r", addr)

    while True:
        try:
            remote_sock, addr = sock.accept()
        except OSError as e:
            logger.debug(
                'Got exception listening for socket connection %r', e)
            continue
        msg = _get(remote_sock)
        cmd, *args = shlex.split(msg)
        # calculate
        try:
            result = cmd_dict[cmd](*args)
        except KeyError as e:
            logger.warning('KeyError in server mainloop %r', e)
            continue
        except TypeError as e:
            logger.warning('TypeError in server mainloop %r', e)
            continue
        # send data
        if result is not None:
            remote_sock.send(wrap(result))
        else:
            remote_sock.send(bytes([0]))

        remote_sock.shutdown(socket.SHUT_RDWR)
        remote_sock.close()


def wrap(chars):
    x = chars.encode('utf8')
    assert len(x) < 256
    return bytes([len(x)]) + chars.encode('utf8')


def _get(sock):
    size = sock.recv(1)
    if not size:
        return None
    return sock.recv(size).decode('utf8')


def _close(sock):
    sock.shutdown(socket.SHUT_RDWR)
    sock.close()
