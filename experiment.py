# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

from random import randrange
import klibs
from klibs import P
from klibs.KLGraphics import KLDraw as kld
from klibs.KLConstants import STROKE_INNER
from klibs.KLCommunication import message
from klibs.KLGraphics import fill, flip
from klibs.KLUserInterface import key_pressed, pump, ui_request
from klibs.KLBoundary import BoundarySet, RectangleBoundary

from pyfirmata import serial


# Arduino trigger values (for PLATO goggles)
OPEN = b"55"
CLOSE = b"56"

# fixation and rectangle are placed
OFFSET = 21  # cms above screen bottom (horizontally centered)

# Stimulus sizes
UNIT = 9  # 9 mm; converted to px at runtime
CIRCLE_DIAM = 2  # this & rest are multiples of UNIT
RECT_WIDTH = 13
RECT_HEIGHT = 9
FIX_WIDTH = 2
THICKNESS = 0.3  # thickness of stimulus outlines

# Colors
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
WHITE = (255, 255, 255, 255)

# Color-outcome mappings
PENALTY_OUTLINE = RED
PENALTY_FILL = RED
REWARD_OUTLINE = GREEN
REWARD_FILL = None

# Point values
REWARD_PAYOUT = 100
PENALTY_PAYOUT = -600
VENN_PAYOUT = -500
MISS_PAYOUT = -700
TIMEOUT_PAYOUT = 0


class reward_feedback_pointing_2025(klibs.Experiment):

    def setup(self):

        # Handles communication with arduino (goggles)
        self.goggles = serial.Serial(port="COM6", baudrate=9600)

        #
        #   Set up visual properties
        #

        # Get px per mm
        self.unit_px = (P.ppi / 25.4) * UNIT

        # Define stimuli
        self.stimuli = {
            "fix": kld.FixationCross(
                size=self.unit_px * FIX_WIDTH, thickness=THICKNESS, fill=WHITE
            ),
            "rect": kld.Rectangle(
                width=self.unit_px * RECT_WIDTH,
                height=self.unit_px * RECT_HEIGHT,
                stroke=[THICKNESS, BLUE, STROKE_INNER],
            ),
            "reward": kld.Circle(
                diameter=self.unit_px * CIRCLE_DIAM,
                fill=REWARD_FILL,
                stroke=[THICKNESS, REWARD_OUTLINE, STROKE_INNER],
            ),
            "penalty": kld.Circle(
                diameter=self.unit_px * CIRCLE_DIAM,
                fill=PENALTY_FILL,
                stroke=[THICKNESS, PENALTY_OUTLINE, STROKE_INNER],
            ),
        }

        self.bounds = BoundarySet()
        self.bounds.add_boundary(
            RectangleBoundary(
                label="rect",
                p1=(
                    (P.screen_x / 2) + (RECT_WIDTH / 2),  # type: ignore[operator]
                    (P.screen_y - OFFSET) - (RECT_HEIGHT / 2),  # type: ignore[operator]
                ),
                p2=(
                    (P.screen_x / 2) - (RECT_WIDTH / 2),  # type: ignore[operator]
                    (P.screen_y - OFFSET) + (RECT_HEIGHT / 2),  # type: ignore[operator]
                ),
            )
        )

        #
        #   Set up condition order
        #

        self.feedback_conditions = (
            ["vision", "reward"]
            if P.condition == "vision"
            else ["reward", "vision"]
        )

        if (
            P.run_practice_blocks
        ):  # Double up on conditions if practice blocks are enabled
            self.feedback_conditions = [cond for cond in self.feedback_conditions for _ in range(2)]
            self.insert_practice_block(block_nums=[1, 3], trial_counts=P.trials_per_practice_block)  # type: ignore[attr-defined]

    def block(self):
        self.goggles.write(OPEN)

        # get task condition for block
        self.current_condition = self.feedback_conditions.pop(0)

        # if no-vision, record point total for presentation
        if self.current_condition == "reward":
            self.point_total = 0

        # TODO: Implement block-specific instructions
        instrux = (
            "(Full instructions TBD)"
            "\n\n"
            f"Block condition: {P.condition}"
            "\n\n"
            "Press the spacebar to begin the block."
        )

        if P.practicing:
            instrux += "\n(this is a practice block)"

        # Present instructions
        fill()
        message(text=instrux, location=P.screen_c, blit_txt=True)
        flip()

        # Wait for spacebar press to start running trials
        while True:
            # Monitor for any commands to quit, etc
            q = pump(True)
            _ = ui_request(queue=q)
            if key_pressed("space"):
                break

    def trial_prep(self):
        pass

    def trial(self):  # type: ignore[override]

        return {"block_num": P.block_number, "trial_num": P.trial_number}

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    def get_circle_placements(self):
        rad_px = (CIRCLE_DIAM / 2) * self.unit_px
        padd = 2

        rect_p1 = self.bounds.boundaries["rect"].p1()
        rect_p2 = self.bounds.boundaries["rect"].p2()

        origin_x = randrange(
            start=rect_p1[0] + (1.5 * rad_px) + padd,
            stop=rect_p2[0] - (1.5 * rad_px) - padd
        )
        origin_y = randrange(
            start=rect_p1[1] + rad_px + padd,
            stop=rect_p2[1] - rad_px - padd
        )

        if self.penalty_side == "left":  # type: ignore[attr-defined]
            return {
                "penalty": (origin_x - rad_px, origin_y),
                "reward": (origin_x + rad_px, origin_y)
            }
        else:
            return {
                "reward": (origin_x - rad_px, origin_y),
                "penalty": (origin_x + rad_px, origin_y)
            }
