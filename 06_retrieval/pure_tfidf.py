"""
Pure-Python TF-IDF + cosine similarity (NO sklearn / numpy / scipy).

WHY: Catalyst AppSail does not pip-install dependencies — libraries must be bundled with the
app, and the sklearn+numpy+scipy stack is ~290MB, over the 256MB disk limit. TF-IDF and cosine
similarity are simple enough to implement directly, so we drop ~265MB of dependencies.

Faithfully replicates sklearn's TfidfVectorizer(stop_words="english", ngram_range=(1,2), min_df=1):
  - token pattern  : (?u)\\b\\w\\w+\\b  (words of 2+ chars), lowercased
  - stop words     : sklearn's exact ENGLISH_STOP_WORDS list (below)
  - ngrams         : unigrams + bigrams, built AFTER stopword removal (sklearn's behavior)
  - idf            : smooth_idf -> ln((1+n)/(1+df)) + 1
  - tf             : raw counts (sublinear_tf=False)
  - norm           : L2
  - similarity     : cosine == dot product of L2-normalized vectors
"""
import re, math
from collections import Counter

TOKEN_RE = re.compile(r"(?u)\b\w\w+\b")

ENGLISH_STOP_WORDS = frozenset(['a', 'about', 'above', 'across', 'after', 'afterwards', 'again', 'against', 'all', 'almost', 'alone', 'along', 'already', 'also', 'although', 'always', 'am', 'among', 'amongst', 'amoungst', 'amount', 'an', 'and', 'another', 'any', 'anyhow', 'anyone', 'anything', 'anyway', 'anywhere', 'are', 'around', 'as', 'at', 'back', 'be', 'became', 'because', 'become', 'becomes', 'becoming', 'been', 'before', 'beforehand', 'behind', 'being', 'below', 'beside', 'besides', 'between', 'beyond', 'bill', 'both', 'bottom', 'but', 'by', 'call', 'can', 'cannot', 'cant', 'co', 'con', 'could', 'couldnt', 'cry', 'de', 'describe', 'detail', 'do', 'done', 'down', 'due', 'during', 'each', 'eg', 'eight', 'either', 'eleven', 'else', 'elsewhere', 'empty', 'enough', 'etc', 'even', 'ever', 'every', 'everyone', 'everything', 'everywhere', 'except', 'few', 'fifteen', 'fifty', 'fill', 'find', 'fire', 'first', 'five', 'for', 'former', 'formerly', 'forty', 'found', 'four', 'from', 'front', 'full', 'further', 'get', 'give', 'go', 'had', 'has', 'hasnt', 'have', 'he', 'hence', 'her', 'here', 'hereafter', 'hereby', 'herein', 'hereupon', 'hers', 'herself', 'him', 'himself', 'his', 'how', 'however', 'hundred', 'i', 'ie', 'if', 'in', 'inc', 'indeed', 'interest', 'into', 'is', 'it', 'its', 'itself', 'keep', 'last', 'latter', 'latterly', 'least', 'less', 'ltd', 'made', 'many', 'may', 'me', 'meanwhile', 'might', 'mill', 'mine', 'more', 'moreover', 'most', 'mostly', 'move', 'much', 'must', 'my', 'myself', 'name', 'namely', 'neither', 'never', 'nevertheless', 'next', 'nine', 'no', 'nobody', 'none', 'noone', 'nor', 'not', 'nothing', 'now', 'nowhere', 'of', 'off', 'often', 'on', 'once', 'one', 'only', 'onto', 'or', 'other', 'others', 'otherwise', 'our', 'ours', 'ourselves', 'out', 'over', 'own', 'part', 'per', 'perhaps', 'please', 'put', 'rather', 're', 'same', 'see', 'seem', 'seemed', 'seeming', 'seems', 'serious', 'several', 'she', 'should', 'show', 'side', 'since', 'sincere', 'six', 'sixty', 'so', 'some', 'somehow', 'someone', 'something', 'sometime', 'sometimes', 'somewhere', 'still', 'such', 'system', 'take', 'ten', 'than', 'that', 'the', 'their', 'them', 'themselves', 'then', 'thence', 'there', 'thereafter', 'thereby', 'therefore', 'therein', 'thereupon', 'these', 'they', 'thick', 'thin', 'third', 'this', 'those', 'though', 'three', 'through', 'throughout', 'thru', 'thus', 'to', 'together', 'too', 'top', 'toward', 'towards', 'twelve', 'twenty', 'two', 'un', 'under', 'until', 'up', 'upon', 'us', 'very', 'via', 'was', 'we', 'well', 'were', 'what', 'whatever', 'when', 'whence', 'whenever', 'where', 'whereafter', 'whereas', 'whereby', 'wherein', 'whereupon', 'wherever', 'whether', 'which', 'while', 'whither', 'who', 'whoever', 'whole', 'whom', 'whose', 'why', 'will', 'with', 'within', 'without', 'would', 'yet', 'you', 'your', 'yours', 'yourself', 'yourselves'])


def _analyze(text):
    """Tokenize -> lowercase -> drop stopwords -> unigrams + bigrams (sklearn's order)."""
    toks = [t for t in TOKEN_RE.findall((text or "").lower()) if t not in ENGLISH_STOP_WORDS]
    feats = list(toks)                                   # unigrams
    feats += [f"{toks[i]} {toks[i+1]}" for i in range(len(toks) - 1)]   # bigrams
    return feats


class PureTfidf:
    """Drop-in replacement for the TfidfVectorizer + cosine_similarity usage in retrieval."""

    def __init__(self):
        self.vocab = {}      # term -> index
        self.idf = {}        # term -> idf weight
        self.doc_vecs = []   # list of {term_index: weight}, L2-normalized

    def fit_transform(self, texts):
        docs = [_analyze(t) for t in texts]
        n = len(docs)

        # document frequency
        df = Counter()
        for d in docs:
            for term in set(d):
                df[term] += 1

        # vocabulary (min_df=1 -> every term kept)
        self.vocab = {term: i for i, term in enumerate(sorted(df))}

        # smooth idf, exactly as sklearn: ln((1+n)/(1+df)) + 1
        self.idf = {term: math.log((1 + n) / (1 + df[term])) + 1.0 for term in df}

        self.doc_vecs = [self._vectorize(d) for d in docs]
        return self.doc_vecs

    def _vectorize(self, feats):
        """Counts -> tf*idf -> L2 normalize. Returns a sparse dict {index: weight}."""
        counts = Counter(feats)
        vec = {}
        for term, tf in counts.items():
            if term in self.vocab:                       # unseen terms ignored (like sklearn)
                vec[self.vocab[term]] = tf * self.idf[term]
        norm = math.sqrt(sum(w * w for w in vec.values()))
        if norm > 0:
            for k in vec:
                vec[k] /= norm
        return vec

    def transform_one(self, text):
        return self._vectorize(_analyze(text))

    @staticmethod
    def cosine(v1, v2):
        """Both vectors are L2-normalized, so cosine == dot product. Iterate the smaller one."""
        if len(v1) > len(v2):
            v1, v2 = v2, v1
        return sum(w * v2.get(i, 0.0) for i, w in v1.items())

    def query(self, text, k=5):
        """Return [(doc_index, score), ...] for the top-k most similar docs."""
        q = self.transform_one(text)
        sims = [(i, self.cosine(q, dv)) for i, dv in enumerate(self.doc_vecs)]
        sims = [(i, s) for i, s in sims if s > 0]
        sims.sort(key=lambda x: -x[1])
        return sims[:k]
