from functools import lru_cache
import logging
import abc
from functools import partial
import random
from operator import itemgetter
from collections import defaultdict
from numbers import Number
from itertools import repeat

import pymysql

logger = logging.getLogger(__name__)

GRAPH_THRESHOLD = 4
INITIAL_FREQ = 0.01


class Database(BaseDatabase):

    def __init__(self, *args, **kwargs):
        self._args = args
        self._kwargs = kwargs

    def _connect(self):
        return pymysql.connect(*self._args, **self._kwargs)

    def hasword(self, word):
        with self._connect() as cur:
            cur.execute('SELECT id FROM words WHERE word=%s', word)
            x = cur.fetchone()
            if x:
                return True
            else:
                return False

    def wordfromid(self, id):
        with self._connect() as cur:
            cur.execute('SELECT word FROM words WHERE id=%s', id)
            return cur.fetchone()[0].decode('utf8')

    def freq(self, id):
        with self._connect() as cur:
            cur.execute('SELECT frequency FROM words WHERE id=%s', id)
            count = cur.fetchone()[0]
            assert isinstance(count, Number)
            cur.execute('SELECT sum(frequency) FROM words')
            total = cur.fetchone()[0]
            assert isinstance(total, Number)
            return count / total

    def length_between(self, a, b):
        with self._connect() as cur:
            cur.execute(
                'SELECT id FROM words WHERE length BETWEEN %s AND %s',
                (a, b))
            return [x[0] for x in cur.fetchall()]

    def len_startswith(self, a, b, prefix):
        with self._connect() as cur:
            cur.execute(' '.join((
                'SELECT id FROM words WHERE length BETWEEN %s AND %s',
                'AND word LIKE %s')), (a, b, prefix + '%'))
            return [x[0] for x in cur.fetchall()]

    def startswith(self, a):
        with self._connect() as cur:
            cur.execute(
                'SELECT id FROM words WHERE word LIKE %s', a + '%')
            return [x[0] for x in cur.fetchall()]

    def neighbors(self, word_id):
        with self._connect() as cur:
            cur.execute(
                'SELECT word2 FROM graph WHERE word1=%s',
                word_id)
            return [x[0] for x in cur.fetchall()]

    def add_word(self, word, freq):
        logger.debug('add_word(%r, %r)', word, freq)
        with self._connect() as cur:
            cur.execute('SELECT sum(frequency) FROM words')
            total_freq = cur.fetchone()[0]
            assert isinstance(total_freq, Number)
            cur.execute(' '.join((
                    'INSERT IGNORE INTO words SET',
                    'word=%s, length=%s, frequency=%s',)),
                (word, len(word), total_freq * freq))
            cur.execute('SELECT LAST_INSERT_ID()')
            id = cur.fetchone()[0]
            assert isinstance(id, int)
            cur.execute('SELECT id, word FROM words')
            wordlist = [(a, b.decode('utf8')) for a, b in cur.fetchall()]
            cur.executemany(' '.join((
                'INSERT IGNORE INTO graph (word1, word2) VALUES',
                '(%s, %s), (%s, %s)',)),
                ((x, y, y, x) for x, y in zip(
                    repeat(id), self._gen_graph(word, wordlist))))

    @staticmethod
    def _gen_graph(target, wordlist):
        logger.debug('_gen_graph(%r, wordlist)', target)
        threshold = GRAPH_THRESHOLD
        for id, word in wordlist:
            if editdist(word, target, threshold) < threshold:
                yield id

    def add_freq(self, word, freq):
        with self._connect() as cur:
            cur.execute(
                'UPDATE words SET frequency=frequency + %s WHERE word=%s',
                (word, freq))

    def balance_freq(self):
        raise NotImplementedError


class Spell:

    LOOKUP_THRESHOLD = 3
    LENGTH_ERR = 2

    def __init__(self, db):
        self.db = db

    def check(self, word):
        if self.db.hasword(word):
            return 'OK'
        else:
            return 'ERROR'

    def correct(self, word):

        logger.debug('correct(%r)', word)
        assert isinstance(word, str)

        # get initial candidates
        length = len(word)
        id_cands = self.db.len_startswith(
            length - self.LENGTH_ERR, length + self.LENGTH_ERR, word[0])
        if not id_cands:
            logger.debug('no candidates')
            return None

        # select inital candidate
        id_cand = random.choice(id_cands)
        while editdist(id_cand, word) > self.LOOKUP_THRESHOLD:
            id_cand = random.choice(id_cands)
        id_cands = []
        dist_cands = []
        id_cands.append(id_cand)
        dist_cands.append(editdist(id_cands))

        # traverse graph
        self._explore(word, id_cands, dist_cands, id_cand)
        candidates = [(id, self._cost(dist, id, word))
                      for id, dist in zip(id_cands, dist_cands)]
        id, cost = max(candidates, key=itemgetter(1))
        return self.db.wordfromid(id)

    def _explore(self, word, id_cands, dist_cands, id_node):
        """
        Args:
            word: misspelled word
            id_cands: candidate ids
            dist_cand: candidate distance for misspelled word
            id_node: current node

        """
        id_new = set()
        for id_neighbor in self.db.neighbors(id_node):
            if id_node not in id_cands:
                dist = editdist(word, self.db.wordfromid(id_node))
                if dist <= self.LOOKUP_THRESHOLD:
                    id_cands.append(id_neighbor)
                    dist_cands.append(dist)
                    id_new.add(id_neighbor)
        for id_node in id_new:
            self._explore(word, id_cands, dist_cands, id_node)

    def process(self, word):
        if self.check(word) == 'OK':
            return 'OK'
        else:
            correct = self.correct(word)
            return ' '.join(('WRONG', correct if correct is not None else ''))

    def add(self, word):
        self.db.add_word(word, INITIAL_FREQ)

    def bump(self, word):
        self.db.add_freq(word, 1)

    def update(self, word):
        if not self.db.hasword(word):
            self.add(word)
        else:
            self.bump(word)

    def _cost(self, dist, id_word, target):
        """
        Args:
            dist: Distance between words
            id_word: ID of word in graph
            target: Misspelled word

        >>> spell.cost(editdist(word, misspelled), word, misspelled)

        """
        cost = dist
        cost += abs(len(target) - len(word)) / 2
        word = self.db.wordfromid(id_word)
        if target[0] != word[0]:
            cost += 1
        cost *= self.db.freq(id_word)
        return cost


class Costs:

    keys = 'qwertyuiopasdfghjklzxcvbnm-\''

    _neighbors = {
        'q': ('w', 'a', 's'),
        'w': ('q', 'a', 's', 'd', 'e'),
        'e': ('w', 's', 'd', 'f', 'r'),
        'r': ('e', 'd', 'f', 'g', 't'),
        't': ('r', 'f', 'g', 'h', 'y'),
        'y': ('t', 'g', 'h', 'j', 'u'),
        'u': ('y', 'h', 'j', 'k', 'i'),
        'i': ('u', 'j', 'k', 'l', 'o'),
        'o': ('i', 'k', 'l', 'p'),
        'p': ('o', 'l', '-', "'"),
        'a': ('q', 'w', 's', 'x', 'z'),
        's': ('q', 'a', 'z', 'x', 'c', 'd', 'e', 'w'),
        'd': ('w', 's', 'x', 'c', 'v', 'f', 'r', 'e'),
        'f': ('e', 'd', 'c', 'v', 'b', 'g', 't', 'r'),
        'g': ('r', 'f', 'v', 'b', 'h', 'y', 't'),
        'h': ('t', 'g', 'b', 'n', 'j', 'u', 'y'),
        'j': ('y', 'h', 'n', 'm', 'k', 'i', 'u'),
        'k': ('u', 'j', 'm', 'l', 'o', 'i'),
        'l': ('i', 'k', 'o', 'p'),
        'z': ('a', 's', 'x'),
        'x': ('z', 's', 'd', 'c'),
        'c': ('x', 'd', 'f', 'v'),
        'v': ('c', 'f', 'g', 'b'),
        'b': ('v', 'g', 'h', 'n'),
        'n': ('b', 'h', 'j', 'm'),
        'm': ('n', 'j', 'k', 'l'),
        '-': ('p',),
        "'": ('p',),
    }

    def __init__(self):
        self.costs = [
            [float('+inf') for i in range(len(self.keys))]
            for j in range(len(self.keys))]

    def get(self, a, b):
        return self.costs[self.keys.index(a)][self.keys.index(b)]

    def set(self, a, b, v):
        self.costs[self.keys.index(a)][self.keys.index(b)] = v

    def compute(self):
        for a in self._neighbors:
            logger.debug('Computing for a=%r', a)
            unvisited = set(self.keys)
            self.set(a, a, 0)
            while unvisited:
                current = min(unvisited, key=partial(self.get, a))
                logger.debug('Computing for current=%r', current)
                for k in self._neighbors[current]:
                    if k not in unvisited:
                        continue
                    else:
                        self.set(a, k, min(
                            self.get(a, k), self.get(a, current) + 0.5))
                unvisited.remove(current)

    def print(self):
        for i, x in enumerate(self.keys):
            print(x)
            print(', '.join(
                ': '.join((y, str(self.costs[i][j])))
                for j, y in enumerate(self.keys)))

    def repl_cost(self, a, b):
        logger.debug('repl_cost(%r, %r)', a, b)
        assert isinstance(a, str) and len(a) == 1
        assert isinstance(b, str) and len(b) == 1
        cost = self.get(a, b)
        assert cost is not None
        return cost

costs = Costs()
costs.compute()


@lru_cache(2048)
def editdist(a, b, limit=None):
    try:
        return _editdist(a, b, limit)
    except LimitException:
        return float('+inf')


@lru_cache(2048)
def _editdist(a, b, limit):
    """
    Parameters
    ----------
    a : str
        Word substring to calculate edit distance for
    b : str
        Word substring to calculate edit distance for
    limit : Number or None
        Cost limit before returning

    """
    logger.debug(
        '_editdist(%r, %r, %r)', a, b, limit)
    if i_word < 0 or i_target < 0:
        logger.debug('Got inf')
        return float('+inf')
    possible = [float('+inf')]
    # insert in a
    try:
        possible.append(_editdist(a, b[:-1], limit) + 1)
    except IndexError:
        pass
    # delete in a
    try:
        possible.append(_editdist(a[:-1], b, limit) + 1)
    except IndexError:
        pass
    # replace or same
    try:
        possible.append(
            editdist(a[:-1], b[:-1], limit) +
            costs.repl_cost(a[-1], b[-1]))
    except IndexError:
        pass
    # transposition
    try:
        if a[-1] == b[-2] and a[-2] == b[-1]:
            possible.append(
                editdist(a[:-2], b[:-2], limit) + 1)
    except IndexError:
        pass
    cost = min(possible)
    if limit is not None and cost >= limit:
        raise LimitException
    return cost


class LimitException(Exception):
    pass
