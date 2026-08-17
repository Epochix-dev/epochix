/**
 * Classical ML in the terminal: XGBoost, LightGBM, CatBoost, sklearn loops.
 *
 * The detector decides whether the dashboard opens itself, and it only knew
 * neural-network shapes. An XGBoost run scored 0.15 against a 0.45 threshold,
 * so the headline feature — start training, the dashboard appears — simply did
 * not happen for anyone doing gradient boosting or regression.
 *
 * The samples are real library output, not written from memory: XGBoost
 * separates columns with tabs and names eval sets by position, LightGBM puts an
 * apostrophe inside the metric name. Guessing at those is how the Python parser
 * got them wrong in the first place.
 */
import * as assert from "assert";

import { computeGrade, hasAbsoluteScale } from "../../story/grader";
import { isTraining, sniff } from "../../terminal/TrainingDetector";

const XGBOOST = [
  "[0]\tvalidation_0-logloss:0.51987\tvalidation_1-logloss:0.52369",
  "[1]\tvalidation_0-logloss:0.40326\tvalidation_1-logloss:0.41045",
  "[2]\tvalidation_0-logloss:0.31963\tvalidation_1-logloss:0.33034",
].join("\n");

const XGBOOST_REGRESSION = [
  "[0]\tvalidation_0-rmse:183.17352",
  "[1]\tvalidation_0-rmse:171.87354",
].join("\n");

const LIGHTGBM = ["[2]\tvalid_0's l2: 30497.7", "[4]\tvalid_0's l2: 25082.4"].join("\n");

const CATBOOST = [
  "0:\tlearn: 0.6798710\ttest: 0.6801448\tbest: 0.6801448 (0)",
  "1:\tlearn: 0.6712004\ttest: 0.6725513\tbest: 0.6725513 (1)",
].join("\n");

const SGD_LOOP = [
  "iter 1 rmse 15.2038 r2 0.9939",
  "iter 2 rmse 13.9910 r2 0.9948",
  "iter 3 rmse 13.1122 r2 0.9953",
].join("\n");

/** Output that must NOT open a dashboard. */
const NOT_TRAINING = [
  "Requirement already satisfied: numpy in ./venv/lib/python3.12/site-packages",
  "Reading package lists... Done",
  "[1] 12345 running in background",
  "npm WARN deprecated round 3 of retries",
  "Cloning into 'repo'... iteration 2 complete",
  "[2024-01-01 10:00:00] INFO: server started on port 8080",
];

suite("Classical ML is recognised as training", () => {
  test("XGBoost classification opens the dashboard", () => {
    assert.ok(isTraining(XGBOOST), `scored ${sniff(XGBOOST)}`);
  });

  test("XGBoost regression opens the dashboard", () => {
    assert.ok(isTraining(XGBOOST_REGRESSION), `scored ${sniff(XGBOOST_REGRESSION)}`);
  });

  test("LightGBM opens the dashboard", () => {
    assert.ok(isTraining(LIGHTGBM), `scored ${sniff(LIGHTGBM)}`);
  });

  test("CatBoost opens the dashboard", () => {
    assert.ok(isTraining(CATBOOST), `scored ${sniff(CATBOOST)}`);
  });

  test("an iteration loop reporting RMSE opens the dashboard", () => {
    // Needs the counter AND a named metric. Regression had no signal here at
    // all, so a loop printing RMSE and R² scored zero.
    assert.ok(isTraining(SGD_LOOP), `scored ${sniff(SGD_LOOP)}`);
  });

  NOT_TRAINING.forEach((line) => {
    test(`stays quiet: ${line.slice(0, 40)}`, () => {
      assert.ok(
        !isTraining(line),
        `opened on non-training output (scored ${sniff(line)}): ${line}`,
      );
    });
  });

  test("a bracketed number alone is not enough", () => {
    // Shell job control and log timestamps both start lines with brackets.
    assert.ok(!isTraining("[1] 12345\n[2] 12346\n[3] 12347"));
  });
});

suite("Regression grading does not depend on the target's units", () => {
  // The standalone engine grades without Python, so it has its own copy of the
  // thresholds. When the Python side learned that regression bands are MAE
  // bands — and that MAE carries the target's units — this copy had to learn it
  // too, or the same log gets one grade with the sidecar and another without.

  test("an excellent fit is not an F", () => {
    // A real Ridge run: R² 0.9960, graded F because its targets ran into the
    // hundreds and the bands were written for normalised ones.
    assert.strictEqual(computeGrade("regression", 0.996, "R2"), "A+");
  });

  test("the scale runs the right way", () => {
    // regression is a lower-is-better task, so without metric-aware bands R²
    // was scored upside down as well as against the wrong ruler.
    assert.strictEqual(computeGrade("regression", 0.91, "R2"), "A");
    assert.strictEqual(computeGrade("regression", 0.45, "R2"), "C");
    assert.strictEqual(computeGrade("regression", -3.0, "R2"), "F");
  });

  test("only R2 claims an absolute scale", () => {
    assert.ok(hasAbsoluteScale("R2"));
    assert.ok(hasAbsoluteScale("val_R2"));
    assert.ok(!hasAbsoluteScale("MAE"));
    assert.ok(!hasAbsoluteScale("val_RMSE"));
  });

  test("gaze keeps its absolute bands", () => {
    // Not every MAE is unit-less: gaze MAE is an angle in degrees.
    assert.strictEqual(computeGrade("gaze", 0.4), "A+");
    assert.strictEqual(computeGrade("gaze", 25.0), "F");
  });

  test("classification is untouched", () => {
    assert.strictEqual(computeGrade("classification", 0.96), "A+");
    assert.strictEqual(computeGrade("classification", 0.61), "C");
  });
});
