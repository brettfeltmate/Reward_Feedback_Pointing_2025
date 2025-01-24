# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

import klibs
from klibs import P
from klibs.KLGraphics import KLDraw as kld
from klibs.KLConstants import STROKE_INNER
from klibs.KLCommunication import message
from klibs.KLGraphics import fill, flip
from klibs.KLUserInterface import key_pressed, pump, ui_request

from pyfirmata import serial

from random import randrange, choice

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

        #
        #   Set up condition order
        #

        self.conditions = (
            ["vision", "no_vision"]
            if P.condition == "vision"
            else ["no_vision", "vision"]
        )

        if (
            P.run_practice_blocks
        ):  # Double up on conditions if practice blocks are enabled
            self.conditions = [cond for cond in self.conditions for _ in range(2)]
            self.insert_practice_block(block_nums=[1, 3], trial_counts=P.trials_per_practice_block)  # type: ignore[attr-defined]

    def block(self):
        self.goggles.write(OPEN)

        # get task condition for block
        self.current_condition = self.conditions.pop(0)

        # if no-vision, record point total for presentation
        if self.current_condition == "no_vision":
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
        """
        - Treat venned circles as 2 * 3 unit-sized rectangle

        - Using point located 21 cm up from bottom-center of screen as origin
            - Select X offset from range 0 to (rect_width / 2 - 1.5) * unit
            - Select Y offset from range 0 to (rect_height / 2 - 1) * unit
            - Randomly select sign for both
            - ... maybe add a bit of padding to prevent being flush with edge?

        - Circles' registration points are then:
            - Right circle: x = origin_x - offset_x - (0.5 * unit), y = origin_y
            - Left circle:  x = origin_x - offset_x + (0.5 * unit), y = origin_y
        """

        # Get origin
        origin = [P.screen_c[0], P.screen_y - OFFSET]  # type: ignore[operator]

        # get offsets
        x_offset = randrange(0, int(RECT_WIDTH / 2 - 1.5) * UNIT) * choice([-1, 1])
        y_offset = randrange(0, int(RECT_HEIGHT / 2 - 1) * UNIT) * choice([-1, 1])

        # get circle placements
        right_origin = [origin[0] + x_offset, origin[1] + y_offset]
        left_origin = [origin[0] - x_offset, origin[1] + y_offset]



        pass
