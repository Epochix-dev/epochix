"""Real XGBoost and LightGBM runs on scikit-learn's bundled data, console output kept."""

from __future__ import annotations

import sys

from sklearn.datasets import load_breast_cancer, load_diabetes
from sklearn.model_selection import train_test_split

which = sys.argv[1]

if which == "xgb_clf":
    import xgboost as xgb

    x, y = load_breast_cancer(return_X_y=True)
    xt, xv, yt, yv = train_test_split(x, y, test_size=0.25, random_state=3)
    model = xgb.XGBClassifier(
        n_estimators=60, learning_rate=0.1, max_depth=3, eval_metric=["logloss", "error"]
    )
    model.fit(xt, yt, eval_set=[(xt, yt), (xv, yv)], verbose=True)
elif which == "xgb_reg":
    import xgboost as xgb

    x, y = load_diabetes(return_X_y=True)
    xt, xv, yt, yv = train_test_split(x, y, test_size=0.25, random_state=3)
    model = xgb.XGBRegressor(n_estimators=80, learning_rate=0.1, max_depth=3, eval_metric="rmse")
    model.fit(xt, yt, eval_set=[(xt, yt), (xv, yv)], verbose=True)
elif which == "lgb_clf":
    import lightgbm as lgb

    x, y = load_breast_cancer(return_X_y=True)
    xt, xv, yt, yv = train_test_split(x, y, test_size=0.25, random_state=3)
    model = lgb.LGBMClassifier(n_estimators=60, learning_rate=0.1, num_leaves=15)
    model.fit(
        xt,
        yt,
        eval_set=[(xt, yt), (xv, yv)],
        eval_metric=["binary_logloss", "auc"],
        callbacks=[lgb.log_evaluation(1)],
    )
elif which == "lgb_native":
    import lightgbm as lgb

    x, y = load_diabetes(return_X_y=True)
    xt, xv, yt, yv = train_test_split(x, y, test_size=0.25, random_state=3)
    train, valid = lgb.Dataset(xt, yt), lgb.Dataset(xv, yv)
    lgb.train(
        {"objective": "regression", "metric": ["l2", "l1"], "learning_rate": 0.1, "num_leaves": 15},
        train,
        num_boost_round=80,
        valid_sets=[train, valid],
        valid_names=["train", "valid"],
        callbacks=[lgb.log_evaluation(1), lgb.early_stopping(10)],
    )
