"""Train a real seq2seq model with attention and keep Lightning's own console output.

French -> English translation on the sentence pairs from the PyTorch tutorial
"Translation with a Sequence to Sequence Network and Attention": a GRU encoder,
a GRU decoder with additive (Bahdanau) attention, teacher forcing. As in the
tutorial, only short sentences that start with a common English prefix ("i am",
"he is", ...) are kept, about ten thousand pairs; one in ten is held out for
validation.

    Needs:  pip install lightning
            data/eng-fra.txt   from download.pytorch.org/tutorial/data.zip (3 MB)
    Run:    python seq2seq_attention_source.py > seq2seq_attention.log 2>&1

`val_acc` is token accuracy with teacher forcing: the share of next words the
decoder gets right when given the correct previous words. Nothing is edited
afterwards: the log is the console output, progress-bar redraws included.
"""

from __future__ import annotations

import random
import re
import unicodedata
import warnings
from pathlib import Path

import lightning as L
import torch
import torch.nn.functional as F
from lightning.pytorch.callbacks import TQDMProgressBar
from torch import nn
from torch.utils.data import DataLoader

HERE = Path(__file__).resolve().parent
MAX_WORDS = 10
EPOCHS = 20
BATCH = 64
HIDDEN = 256
SEED = 13
PAD, SOS, EOS = 0, 1, 2
PREFIXES = (
    "i am ",
    "i m ",
    "he is ",
    "he s ",
    "she is ",
    "she s ",
    "you are ",
    "you re ",
    "we are ",
    "we re ",
    "they are ",
    "they re ",
)

# Python warnings print the path of the file that raised them; this log ships
# with the package, so it carries no machine paths.
warnings.filterwarnings("ignore")


def normalise(text: str) -> str:
    text = "".join(
        c
        for c in unicodedata.normalize("NFD", text.lower().strip())
        if unicodedata.category(c) != "Mn"
    )
    text = re.sub(r"([.!?])", r" \1", text)
    return re.sub(r"[^a-zA-Z.!?]+", " ", text).strip()


def load_pairs() -> list[tuple[list[str], list[str]]]:
    pairs = []
    for line in (HERE / "data" / "eng-fra.txt").read_text(encoding="utf-8").splitlines():
        eng, fra = (normalise(s) for s in line.split("\t")[:2])
        src, tgt = fra.split(), eng.split()
        if len(src) < MAX_WORDS and len(tgt) < MAX_WORDS and eng.startswith(PREFIXES):
            pairs.append((src, tgt))
    return pairs


class Vocab:
    def __init__(self, sentences: list[list[str]]) -> None:
        words = sorted({w for s in sentences for w in s})
        self.index = {w: i + 3 for i, w in enumerate(words)}
        self.size = len(words) + 3

    def encode(self, sentence: list[str]) -> list[int]:
        return [self.index[w] for w in sentence] + [EOS]


def collate(batch: list[tuple[list[int], list[int]]]) -> tuple[torch.Tensor, torch.Tensor]:
    def pad(seqs: list[list[int]]) -> torch.Tensor:
        width = max(len(s) for s in seqs)
        return torch.tensor([s + [PAD] * (width - len(s)) for s in seqs])

    return pad([b[0] for b in batch]), pad([b[1] for b in batch])


class BahdanauAttention(nn.Module):
    def __init__(self, hidden: int) -> None:
        super().__init__()
        self.query = nn.Linear(hidden, hidden)
        self.keys = nn.Linear(hidden, hidden)
        self.score = nn.Linear(hidden, 1)

    def forward(self, query: torch.Tensor, keys: torch.Tensor, mask: torch.Tensor) -> torch.Tensor:
        scores = self.score(torch.tanh(self.query(query).unsqueeze(1) + self.keys(keys))).squeeze(
            -1
        )
        weights = F.softmax(scores.masked_fill(~mask, float("-inf")), dim=-1)
        return torch.bmm(weights.unsqueeze(1), keys).squeeze(1)


class Seq2Seq(L.LightningModule):
    def __init__(self, src_vocab: int, tgt_vocab: int) -> None:
        super().__init__()
        self.src_embedding = nn.Embedding(src_vocab, HIDDEN, padding_idx=PAD)
        self.encoder = nn.GRU(HIDDEN, HIDDEN, batch_first=True)
        self.tgt_embedding = nn.Embedding(tgt_vocab, HIDDEN, padding_idx=PAD)
        self.attention = BahdanauAttention(HIDDEN)
        self.decoder = nn.GRU(2 * HIDDEN, HIDDEN, batch_first=True)
        self.head = nn.Linear(HIDDEN, tgt_vocab)
        self.dropout = nn.Dropout(0.1)

    def forward(self, src: torch.Tensor, tgt: torch.Tensor) -> torch.Tensor:
        memory, hidden = self.encoder(self.dropout(self.src_embedding(src)))
        mask = src != PAD
        # Teacher forcing: the decoder is fed the correct previous word.
        previous = torch.cat([torch.full_like(tgt[:, :1], SOS), tgt[:, :-1]], dim=1)
        embedded = self.dropout(self.tgt_embedding(previous))
        logits = []
        for step in range(tgt.shape[1]):
            context = self.attention(hidden[-1], memory, mask)
            out, hidden = self.decoder(
                torch.cat([embedded[:, step], context], dim=-1).unsqueeze(1), hidden
            )
            logits.append(self.head(out.squeeze(1)))
        return torch.stack(logits, dim=1)

    def _loss_and_accuracy(
        self, batch: tuple[torch.Tensor, torch.Tensor]
    ) -> tuple[torch.Tensor, torch.Tensor]:
        src, tgt = batch
        logits = self(src, tgt)
        loss = F.cross_entropy(logits.flatten(0, 1), tgt.flatten(), ignore_index=PAD)
        words = tgt != PAD
        accuracy = ((logits.argmax(-1) == tgt) & words).sum() / words.sum()
        return loss, accuracy

    def training_step(self, batch: tuple[torch.Tensor, torch.Tensor], _: int) -> torch.Tensor:
        loss, accuracy = self._loss_and_accuracy(batch)
        self.log("train_loss", loss, prog_bar=True, on_step=False, on_epoch=True)
        self.log("train_acc", accuracy, prog_bar=True, on_step=False, on_epoch=True)
        return loss

    def validation_step(self, batch: tuple[torch.Tensor, torch.Tensor], _: int) -> None:
        loss, accuracy = self._loss_and_accuracy(batch)
        self.log("val_loss", loss, prog_bar=True)
        self.log("val_acc", accuracy, prog_bar=True)

    def configure_optimizers(self) -> torch.optim.Optimizer:
        return torch.optim.Adam(self.parameters(), lr=1e-3)


def main() -> None:
    L.seed_everything(SEED)
    pairs = load_pairs()
    random.Random(SEED).shuffle(pairs)
    src_vocab = Vocab([p[0] for p in pairs])
    tgt_vocab = Vocab([p[1] for p in pairs])
    encoded = [(src_vocab.encode(s), tgt_vocab.encode(t)) for s, t in pairs]
    held_out = len(encoded) // 10
    val, train = encoded[:held_out], encoded[held_out:]
    print(
        f"dataset: French -> English, {len(train)} training pairs, {len(val)} validation pairs, "
        f"{src_vocab.size} French words, {tgt_vocab.size} English words"
    )

    model = Seq2Seq(src_vocab.size, tgt_vocab.size)
    trainer = L.Trainer(
        max_epochs=EPOCHS,
        accelerator="gpu",
        devices=1,
        logger=False,
        enable_checkpointing=False,
        num_sanity_val_steps=0,
        # The tqdm bar writes every epoch's final line when redirected to a
        # file; the Rich one (the default when `rich` is installed) writes
        # only the last. Redrawn every 20 batches, as Lightning's docs advise
        # for output that goes to a file.
        callbacks=[TQDMProgressBar(refresh_rate=20)],
    )
    trainer.fit(
        model,
        DataLoader(train, batch_size=BATCH, shuffle=True, collate_fn=collate),
        DataLoader(val, batch_size=BATCH, collate_fn=collate),
    )


if __name__ == "__main__":
    main()
