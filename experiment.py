# -*- coding: utf-8 -*-

__author__ = "Brett Feltmate"

import klibs
from klibs import P
from klibs.KLExceptions import TrialException
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
    mouse_pos
)
from klibs.KLInternal import now
from klibs.KLBoundary import BoundarySet, CircleBoundary, RectangleBoundary
from klibs.KLTime import CountDown

from pyfirmata import serial

from math import trunc
from random import randrange
from rich.console import Console

from get_key_state import get_key_state  # type: ignore[import]

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

# Simulus onset asynchronies
RECT_ONSET = 1000  # fix (immediate) -> rect
CIRC_ONSET = 500  # rect -> circles
TIMEOUT_AFTER = 750  # circles -> (no) response


class reward_feedback_pointing_2025(klibs.Experiment):

    def setup(self):

        if P.development_mode:
            self.console = Console()
        # Handles communication with arduino (goggles)
        self.goggles = serial.Serial(port="COM6", baudrate=9600)

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
        self.goggles.write(OPEN)

        # get task condition for block
        self.current_condition = self.feedback_conditions.pop(0)
        self.point_total = 0

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
        self.goggles.write(OPEN)
        # determine circle positions
        self.trial_positions = self.get_circle_placements()

        if P.development_mode:
            self.console.log(self.trial_positions)

        # register corresponding touch boundaries
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

        # practice trial have "no" timeout, but code is cleaner if made excessively long instead
        trial_timeout = TIMEOUT_AFTER if not P.practicing else 30000  # 30s when practicing

        # register event timings
        self.evm.add_event("rect_onset", 1000)
        self.evm.add_event("circle_onset", 500, after="rect_onset")
        self.evm.add_event("trial_timeout", trial_timeout, after="circle_onset")

        # present fix and wait for button press to begin
        fill()
        blit(self.stimuli["fix"], location=self.bounds.boundaries["rect"].center, registration=5)  # type: ignore[operator]
        flip()

        while not key_pressed("space"):
            q = pump(True)
            _ = ui_request(queue=q)

    def trial(self):  # type: ignore[override]
        rt = None
        clicked_at = None
        clicked_on = None
        mt = None
        payout = None


        if P.development_mode:
            mouse_pos(position=(P.screen_x // 2, P.screen_y))  # type: ignore[operator]


        # admonish any movements made prior to circle onset
        while self.evm.before("circle_onset"):
            q = pump(True)
            _ = ui_request(queue=q)

            premptive_release = get_key_state("space") == 0

            if premptive_release:
                self.evm.stop_clock()

                msg = message("Please wait until the\ncircles appear before moving.")
                self.draw_display(draw_circles=False, blit_this=(msg, self.bounds.boundaries["rect"].center))
                
                self.wait_for(0.5)

                raise TrialException("Premptive movement")

            # fixed delay before rect presented
            rect_visible = False
            if self.evm.after("rect_onset") and not rect_visible:
                self.draw_display(draw_circles=False)
                rect_visible = True  # don't do redundant redraws


        self.draw_display(draw_circles=True)

        #
        # Response period
        #

        goggles_open = True

        # Listen for responses
        while self.evm.before("trial_timeout") and clicked_on is None:

            while rt is None:
                # log if/when spacebar was released
                key_released = get_key_state("space")
                if key_released:
                    rt = self.evm.time_elapsed

            # in reward condition, close goggles on release
            if self.current_condition == "reward" and goggles_open:
                # self.goggles.write(CLOSE)
                goggles_open = False

            # log where 
            clicked_at, clicked_on = self.listen_for_click()

        # following click or timeout, ensure vision is available, regardless of condition
        if not goggles_open:
            self.goggles.write(OPEN)

        # if click made, get time passed since key release (rt)
        if clicked_on is not None:
            mt = self.evm.time_elapsed - rt  # type: ignore[operator]

        # determine appropriate payout
        payout = self.get_payout(clicked_on)
        self.point_total += payout

        # conditionally select feedback to present
        if P.practicing:  # only provide mt during practice
            if clicked_on is None:
                text = "No response was detected."
            else:
                text = f"Movement time was: {trunc(mt)} ms."  # type: ignore[operation]

            self.draw_display(
                draw_circles=False,
                blit_this=(message(text), self.bounds.boundaries["rect"].center),
            )

            self.wait_for(1)

        else:
            # only present points earned
            if self.current_condition == "reward":

                # for trial
                msg = message(f"Trial payout: {payout}", blit_txt=False)
                self.draw_display(
                    draw_circles=False,
                    blit_this=(msg, self.bounds.boundaries["rect"].center),
                )

                self.wait_for(0.5)

                # overall block total
                msg = message(f"Total points: {self.point_total}")
                self.draw_display(
                    draw_circles=False,
                    blit_this=(msg, self.bounds.boundaries["rect"].center),
                )

            # or, only present touch point
            else:
                self.draw_display(
                    draw_circles=False, blit_this=(self.stimuli["endpoint"], clicked_at)
                )

            # present feedback for 1s
            self.wait_for(1)

        if P.development_mode:
            print("\ntrial()")
            self.console.log(log_locals=True)

        return {
            "practicing": P.practicing,
            "block_num": P.block_number,
            "trial_num": P.trial_number,
            "feedback_condition": self.current_condition if not P.practicing else "NA",
            "reward_side": self.reward_side,  # type: ignore[defined]
            "reward_x": self.trial_positions["reward"][0],
            "reward_y": self.trial_positions["reward"][1],
            "clicked_on": clicked_on if clicked_on is not None else "NA",
            "clicked_x": clicked_at[0] if clicked_at is not None else "NA",
            "clicked_y": clicked_at[1] if clicked_at is not None else "NA",
            "reaction_time": rt,
            "movement_time": mt,
            "trial_payout": payout,
            "total_payout": self.point_total
        }

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

    def listen_for_click(self):
        clicks = get_clicks()
        clicked = None

        if len(clicks) > 1:
            print("Multiple clicks detected. Fix that.")
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

                if P.development_mode:
                    print("\nlisten_for_response()")
                    self.console.log(log_locals=True)

                return clicks[0], clicked
            
        return None, None

    def draw_display(self, draw_circles: bool, blit_this=None):
        if P.development_mode:
            print("\ndraw_display()")
            self.console.log(log_locals=True)
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

        if self.reward_side == "right":  # type: ignore[attr-defined]
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
            print("\nget_circle_placement()")
            self.console.log(log_locals=True)

        return placements

    def wait_for(self, duration: float):
        wait_period = CountDown(duration)
        while wait_period.counting():
            q = pump(True)
            _ = ui_request(queue=q)

