# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

import klibs
from klibs import P
from klibs.KLGraphics import KLDraw as kld
from klibs.KLConstants import STROKE_INNER
from klibs.KLCommunication import message
from klibs.KLGraphics import fill, flip, blit
from klibs.KLUserInterface import (
    key_pressed,
    pump,
    ui_request,
    get_clicks,
    mouse_clicked,
)
from klibs.KLBoundary import BoundarySet, CircleBoundary, RectangleBoundary
from klibs.KLTime import Stopwatch, CountDown

from random import randrange
from rich.console import Console


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
THICKNESS = 0.05  # thickness of stimulus outlines

# Colors
RED = (255, 0, 0, 255)
GREEN = (0, 255, 0, 255)
BLUE = (0, 0, 255, 255)
WHITE = (255, 255, 255, 255)
PURPLE = (255, 0, 255, 255)

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

        if P.development_mode:
            self.console = Console()
        # Handles communication with arduino (goggles)
        # self.goggles = serial.Serial(port="COM6", baudrate=9600)

        #
        #   Set up visual properties
        #

        # Get px per mm
        self.unit_px = (P.ppi / 25.4) * UNIT
        self.offset = self.unit_px * OFFSET
        self.rect_width = self.unit_px * RECT_WIDTH
        self.rect_height = self.unit_px * RECT_HEIGHT
        self.circle_diam = self.unit_px * CIRCLE_DIAM
        self.fix_width = self.unit_px * FIX_WIDTH
        self.thickness = self.unit_px * THICKNESS

        # Define stimuli
        self.stimuli = {
            "fix": kld.FixationCross(
                size=self.fix_width, thickness=self.thickness, fill=WHITE
            ),
            "rect": kld.Rectangle(
                width=self.rect_width,
                height=self.rect_height,
                stroke=[self.thickness, BLUE, STROKE_INNER],
            ),
            "reward": kld.Circle(
                diameter=self.circle_diam,
                fill=REWARD_FILL,
                stroke=[self.thickness, REWARD_OUTLINE, STROKE_INNER],
            ),
            "penalty": kld.Circle(
                diameter=self.circle_diam,
                fill=PENALTY_FILL,
                stroke=[self.thickness, PENALTY_OUTLINE, STROKE_INNER],
            ),
            "endpoint": kld.Asterisk(
                size=self.circle_diam // 2, thickness=self.thickness, fill=PURPLE
            ),
        }

        self.bounds = BoundarySet()
        self.bounds.add_boundary(
            RectangleBoundary(
                label="rect",
                p1=(
                    (P.screen_x / 2) + (self.rect_width / 2),  # type: ignore[operator]
                    (P.screen_y - self.offset) - (self.rect_height / 2),  # type: ignore[operator]
                ),
                p2=(
                    (P.screen_x / 2) - (self.rect_width / 2),  # type: ignore[operator]
                    (P.screen_y - self.offset) + (self.rect_height / 2),  # type: ignore[operator]
                ),
            )
        )

        #
        #   Set up condition order
        #

        self.feedback_conditions = (
            ["vision", "reward"] if P.condition == "vision" else ["reward", "vision"]
        )

        if (
            P.run_practice_blocks
        ):  # Double up on conditions if practice blocks are enabled
            self.feedback_conditions = [
                cond for cond in self.feedback_conditions for _ in range(2)
            ]
            self.insert_practice_block(block_nums=[1, 3], trial_counts=P.trials_per_practice_block)  # type: ignore[attr-defined]

    def block(self):
        # self.goggles.write(OPEN)

        # get task condition for block
        self.current_condition = self.feedback_conditions.pop(0)
        self.point_total = 0

        # if no-vision, record point total for presentation
        # if self.current_condition == "reward":
        #     self.point_total = 0

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
        self.trial_positions = self.get_circle_placements()

        if P.development_mode:
            self.console.log(self.trial_positions)

        self.bounds.add_boundaries(
            [
                CircleBoundary(
                    "penalty", self.trial_positions["penalty"], self.circle_diam / 2
                ),
                CircleBoundary(
                    "reward", self.trial_positions["reward"], self.circle_diam / 2
                ),
            ]
        )

        if P.development_mode:
            self.console.log(self.bounds.boundaries)

        if not P.practicing:
            self.evm.add_event("rect_onset", 1000)
            self.evm.add_event("circle_onset", 500, after="rect_onset")
            self.evm.add_event("timeout", 750, after="circle_onset")

    def trial(self):  # type: ignore[override]
        fill()
        blit(self.stimuli["fix"], location=self.bounds.boundaries["rect"].center, registration=5)  # type: ignore[operator]
        flip()

        # fixed delay before rect presented
        while self.evm.before("rect_onset"):
            q = pump(True)
            _ = ui_request(queue=q)

        self.draw_display(draw_circles=False)

        # wait for click, or
        if P.practicing:
            while not mouse_clicked():
                q = pump(True)
                _ = ui_request(queue=q)

        # wait fixed time to draw circles
        else:
            while self.evm.before("circle_onset"):
                q = pump(True)
                _ = ui_request(queue=q)

        self.draw_display(draw_circles=True)

        #
        # Response period
        #

        clicked_at = None
        clicked_on = None
        movement_time = None
        payout = None

        # no timeout during practice

        movement_timer = Stopwatch()

        if P.practicing:
            while clicked_on is None:
                clicked_at, clicked_on = self.listen_for_response()
                movement_timer.pause()
                movement_time = movement_timer.elapsed()

        else:
            while self.evm.before("timeout") and clicked_on is None:
                clicked_at, clicked_on = self.listen_for_response()
                movement_timer.pause()
                movement_time = movement_timer.elapsed()

        payout = self.get_payout(clicked_on)
        self.point_total += payout

        if P.practicing:
            msg = message(f"Movement time was: {movement_time * 1000} ms.")  # type: ignore[operation]
            self.draw_display(
                draw_circles=False,
                blit_this=(msg, self.bounds.boundaries["rect"].center),
            )

            feedback_duration = CountDown(1)

            while feedback_duration.counting():
                q = pump(True)
                _ = ui_request(queue=q)

        else:
            if self.current_condition == "reward":

                msg = message(f"Trial payout: {payout}", blit_txt=False)
                self.draw_display(
                    draw_circles=False,
                    blit_this=(msg, self.bounds.boundaries["rect"].center),
                )

                feedback_duration = CountDown(0.5)
                while feedback_duration.counting():
                    q = pump(True)
                    _ = ui_request()

                msg = message(f"Total points: {self.point_total}")
                self.draw_display(
                    draw_circles=False,
                    blit_this=(msg, self.bounds.boundaries["rect"].center),
                )

                feedback_duration = CountDown(1)
                while feedback_duration.counting():
                    q = pump(True)
                    _ = ui_request(queue=q)

            else:
                self.draw_display(
                    draw_circles=False, blit_this=(self.stimuli["endpoint"], clicked_at)
                )

                feedback_duration = CountDown(1)
                while feedback_duration.counting():
                    q = pump(True)
                    _ = ui_request(queue=q)

        return {"block_num": P.block_number, "trial_num": P.trial_number}

    def trial_clean_up(self):
        pass

    def clean_up(self):
        pass

    def get_payout(self, clicked_on: str | None):
        if clicked_on is None:
            return TIMEOUT_PAYOUT

        elif clicked_on == "reward":
            return REWARD_PAYOUT

        elif clicked_on == "penalty":
            return PENALTY_PAYOUT

        elif clicked_on == "overlap":
            return VENN_PAYOUT

        else:  # inside rect, outside either circle
            return MISS_PAYOUT

    def listen_for_response(self):
        clicks = get_clicks()
        clicked = None

        if len(clicks) > 1:
            print("Multiple clicks detected; fix it.")
            quit()

        if len(clicks):
            clicked_reward = self.bounds.within_boundary("reward", p=clicks[0])
            clicked_penalty = self.bounds.within_boundary("penalty", p=clicks[0])
            clicked_rect = self.bounds.within_boundary("rect", p=clicks[0])

            if clicked_rect:
                if clicked_reward and not clicked_penalty:
                    clicked = "reward"

                elif clicked_penalty and not clicked_reward:
                    clicked = "penalty"

                elif clicked_reward and clicked_penalty:
                    clicked = "overlap"

                else:
                    clicked = "rect"

        return clicks[0], clicked

    def draw_display(self, draw_circles: bool, blit_this=None):
        fill()

        blit(
            self.stimuli["rect"],
            location=self.bounds.boundaries["rect"].center,
            registration=5,
        )

        if draw_circles:
            blit(
                self.stimuli["penalty"],
                location=self.trial_positions["penalty"],
                registration=5,
            )
            blit(
                self.stimuli["reward"],
                location=self.trial_positions["reward"],
                registration=5,
            )

        if blit_this is not None:
            if len(blit_this) < 2:
                raise ValueError(
                    "draw_display: blit_this must be a two-item list (obj, loc)"
                )
            blit(blit_this[0], location=blit_this[1], registration=5)

        flip()

    def get_circle_placements(self):
        rad_px = self.circle_diam / 2
        circle_offset = 0.5 * rad_px
        padd = self.thickness * 2

        rect_p1 = [int(xy) for xy in self.bounds.boundaries["rect"].p1]
        rect_p2 = [int(xy) for xy in self.bounds.boundaries["rect"].p2]

        if P.development_mode:
            self.console.log((rect_p1, rect_p2))

        origin_x = randrange(
            start=int(rect_p1[0] + (1.5 * rad_px) + padd),
            stop=int(rect_p2[0] - (1.5 * rad_px) - padd),
        )
        origin_y = randrange(
            start=int(rect_p1[1] + rad_px + padd), stop=int(rect_p2[1] - rad_px - padd)
        )

        if P.development_mode:
            self.console.log((origin_x, origin_y))

        if self.penalty_side == "left":  # type: ignore[attr-defined]
            placements = {
                "penalty": (origin_x - circle_offset, origin_y),
                "reward": (origin_x + circle_offset, origin_y),
            }
        else:
            placements = {
                "reward": (origin_x - circle_offset, origin_y),
                "penalty": (origin_x + circle_offset, origin_y),
            }

        if P.development_mode:
            self.console.log(placements)

        return placements
