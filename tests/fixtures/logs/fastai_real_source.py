"""A fastai tabular learner, console output kept.

fastai prints a results table, one row an epoch: `epoch train_loss
valid_loss accuracy time`. Its metrics columns are computed on the validation
set — the column the parser once shifted onto the wrong header.

    Needs:  pip install fastai scikit-learn
    Run:    python fastai_real_source.py > fastai_real.log 2>&1

Run from a neutral folder. scikit-learn's bundled breast-cancer data, CPU.
"""

from __future__ import annotations

import warnings

# Python warnings print the path of the file that raised them, and importing
# fastai raises one from inside torch: filter before the import.
warnings.filterwarnings("ignore")

from fastai.tabular.all import (  # noqa: E402
    CategoryBlock,
    Normalize,
    TabularDataLoaders,
    accuracy,
    set_seed,
    tabular_learner,
)
from sklearn.datasets import load_breast_cancer  # noqa: E402

set_seed(3)
frame = load_breast_cancer(as_frame=True).frame
features = [c for c in frame.columns if c != "target"]
validation = list(range(0, len(frame), 4))
loaders = TabularDataLoaders.from_df(
    frame,
    y_names="target",
    cont_names=features,
    procs=[Normalize],
    y_block=CategoryBlock(),
    valid_idx=validation,
    bs=64,
)
learn = tabular_learner(loaders, layers=[32], metrics=accuracy)
learn.fit(4, lr=1e-2)
