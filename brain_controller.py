from __future__ import annotations

from datetime import datetime

from brain_manager import BrainManager
from learning_engine import LearningEngine
from decision_engine import DecisionEngine
from brain_optimizer import BrainOptimizer


class BrainController:

    def __init__(self):

        self.manager = BrainManager()
        self.learning = LearningEngine()
        self.decision = DecisionEngine()
        self.optimizer = BrainOptimizer()

    # ==========================================================
    # MAIN
    # ==========================================================

    def run(
        self,
        scan_df,
        market_snapshot: dict,
    ):

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        print("")
        print("=" * 70)
        print("🧠 BRAIN START")
        print(now)
        print("=" * 70)

        # -----------------------------------------------------
        # 1. Quan sát
        # -----------------------------------------------------

        observation = self.observe(
            scan_df,
            market_snapshot,
        )

        # -----------------------------------------------------
        # 2. Đánh giá
        # -----------------------------------------------------

        evaluation = self.evaluate(
            observation
        )

        # -----------------------------------------------------
        # 3. Ra quyết định
        # -----------------------------------------------------

        decision = self.decision.make_decision(
            evaluation
        )

        # -----------------------------------------------------
        # 4. Ghi trí nhớ
        # -----------------------------------------------------

        self.manager.save_snapshot(

            observation=observation,

            evaluation=evaluation,

            decision=decision

        )

        # -----------------------------------------------------
        # 5. Học
        # -----------------------------------------------------

        self.learning.learn()

        # -----------------------------------------------------
        # 6. Tối ưu
        # -----------------------------------------------------

        self.optimizer.optimize()

        print("🧠 Brain finished.")

        return {

            "observation": observation,

            "evaluation": evaluation,

            "decision": decision,

        }

    # ==========================================================
    # OBSERVE
    # ==========================================================

    def observe(
        self,
        scan_df,
        market_snapshot,
    ):

        market_real = market_snapshot.get("market_real", 0)

        forecast = market_snapshot.get("forecast", 0)

        breadth = market_snapshot.get("breadth", 0)

        leaders = len(scan_df)

        early = 0
        pull = 0
        strong = 0

        if "group" in scan_df.columns:

            early = (
                scan_df["group"]
                .astype(str)
                .str.contains("EARLY", case=False)
                .sum()
            )

            pull = (
                scan_df["group"]
                .astype(str)
                .str.contains("PULL", case=False)
                .sum()
            )

            strong = (
                scan_df["group"]
                .astype(str)
                .str.contains("MẠNH|STRONG", case=False)
                .sum()
            )

        return {

            "market_real": market_real,

            "forecast": forecast,

            "breadth": breadth,

            "leaders": leaders,

            "early": int(early),

            "pull": int(pull),

            "strong": int(strong),

        }

    # ==========================================================
    # EVALUATE
    # ==========================================================

    def evaluate(
        self,
        observation,
    ):

        score = 0

        score += observation["forecast"] * 2

        score += observation["market_real"]

        score += observation["pull"] * 0.4

        score += observation["early"] * 0.3

        score += observation["strong"] * 0.5

        if score < 10:

            regime = "DEFENSIVE"

        elif score < 25:

            regime = "NEUTRAL"

        else:

            regime = "AGGRESSIVE"

        return {

            "brain_score": round(score, 2),

            "regime": regime,

        }
