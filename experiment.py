# -*- coding: utf-8 -*-

__author__ = 'Brett Feltmate'

import klibs
from klibs import P
from klibs.KLAudio import Tone
from klibs.KLExceptions import TrialException
from klibs.KLGraphics import KLDraw as kld
from klibs.KLConstants import STROKE_INNER
from klibs.KLCommunication import message
from klibs.KLGraphics import fill, flip, blit, clear
from klibs.KLUserInterface import (
    key_pressed,
    pump,
    ui_request,
    get_clicks,
    mouse_pos,
    smart_sleep,
)
from klibs.KLBoundary import BoundarySet, CircleBoundary, RectangleBoundary

from math import trunc
from random import randrange

# For Arduino communication
from pyfirmata import serial

# Trigger values sent to PLATO goggles via Arduino
OPEN = b'55'
CLOSE = b'56'
BAUD = 9600

# Stimulus sizes
UNIT = 9  # 9 mm; converted to px at runtime
CIRCLE_DIAM = 2  # this & rest are multiples of UNIT
OFFSET = 21  # up from screen bottom
RECT_WIDTH = 13
RECT_HEIGHT = 9
FIX_WIDTH = 2
THICKNESS = 0.05  # thickness of stimulus [out]lines

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
MISS_PAYOUT = 0
TIMEOUT_PAYOUT = -700

# Simulus onset asynchronies
RECT_ONSET = 1000  # fix (immediate) -> rect
CIRC_ONSET = 500  # rect -> circles
PREVIEW_WINDOW = 300   # circle onset -> go signal
TIMEOUT_AFTER = 650  # circles -> (no) response

# This way I can't make typos later
COM6 = 'COM6'  # Serial port for arduino communication
START = 'start'
FIX = 'fix'
RECT = 'rect'
REWARD = 'reward'
VISION = 'vision'
PENALTY = 'penalty'
OUTSIDE = 'outside'
OVERLAP = 'overlap'
ENDPOINT = 'endpoint'
SPACE = 'space'
RECTANGLE_ONSET = 'rectangle_onset'
CIRCLE_ONSET = 'circle_onset'
GO_SIGNAL = 'go_signal'
TRIAL_TIMEOUT = 'trial_timeout'
NA = 'NA'


class reward_feedback_pointing_2025(klibs.Experiment):
    # Run first, and once, at the start of the experiment
    def setup(self):

        if P.condition is None:
            raise ValueError(
                'Initial condition (reward, vision) must be specified at runtime\n'
                'using the condition flag (e.g. klibs run 24 -c vision).'
            )
        # Handles communication with arduino (goggles)
        self.goggles = serial.Serial(port=COM6, baudrate=BAUD)

        # Go-signal
        self.go_tone = Tone(100)

        #
        #   Set up visual properties
        #

        # Now that screensize is know, convert sizes to px
        self.unit = (P.ppi / 25.4) * UNIT
        self.offset = self.unit * OFFSET
        self.rect_w = self.unit * RECT_WIDTH
        self.rect_h = self.unit * RECT_HEIGHT
        self.target_circle_d = self.unit * CIRCLE_DIAM
        self.start_circle_d = self.unit * CIRCLE_DIAM * 3
        self.fix_w = self.unit * FIX_WIDTH
        self.thick = self.unit * THICKNESS

        # Define visual stimulus objects
        self.stimuli = {
            START: kld.Circle(
                diameter=self.start_circle_d,
                fill=BLUE,
                stroke=[self.thick, BLUE, STROKE_INNER],
            ),
            FIX: kld.FixationCross(
                size=self.fix_w, thickness=self.thick, fill=WHITE
            ),
            RECT: kld.Rectangle(
                width=self.rect_w,
                height=self.rect_h,
                stroke=[self.thick, BLUE, STROKE_INNER],
            ),
            REWARD: kld.Circle(
                diameter=self.target_circle_d,
                fill=REWARD_FILL,
                stroke=[self.thick, REWARD_OUTLINE, STROKE_INNER],
            ),
            PENALTY: kld.Circle(
                diameter=self.target_circle_d,
                fill=PENALTY_FILL,
                stroke=[self.thick, PENALTY_OUTLINE, STROKE_INNER],
            ),
            ENDPOINT: kld.Asterisk(
                size=self.target_circle_d // 3,
                thickness=self.thick * 2,
                fill=WHITE,
            ),
        }

        # Define boundaries for touch detection
        # TODO: add KLibs feature: accept KLDrawbject, create matching boundary
        self.bs = BoundarySet()
        self.bs.add_boundary(
            CircleBoundary(
                label=START,
                center=(P.screen_x / 2, P.screen_y),  # type: ignore[operator]
                radius=self.start_circle_d / 2,  # type: ignore[operator]
            )
        )
        self.bs.add_boundary(
            RectangleBoundary(
                label=RECT,
                p1=(
                    (P.screen_x / 2) + (self.rect_w / 2),  # type: ignore[operator]
                    (P.screen_y - self.offset) - (self.rect_h / 2),  # type: ignore[operator]
                ),
                p2=(
                    (P.screen_x / 2) - (self.rect_w / 2),  # type: ignore[operator]
                    (P.screen_y - self.offset) + (self.rect_h / 2),  # type: ignore[operator]
                ),
            )
        )

        #
        #   Set up condition order
        #

        # P.condition is set at runtime via klibs' --condition cli flag
        self.conditions = (
            [VISION, REWARD] if P.condition == VISION else [REWARD, VISION]
        )

        # Each condition repeated 3 times in interleaved order for total of 6 blocks
        self.conditions = [cond for cond in self.conditions for _ in range(3)]

        # If desired, insert practice block at start of experiment
        if P.run_practice_blocks:
            self.insert_practice_block(
                block_nums=[1],
                trial_counts=P.trials_per_practice_block,  # type: ignore[attr-defined]
            )

        #
        #   Instruction set
        #

        self.instructions = {
            REWARD: (
                'When you initiate your movement, the goggles will close, and you will not see the target or where you landed.'
                '\n\n'
                'The goggles will re-open at the end of the trial and you will see your points gained/lost on the trial,'
                '\n'
                'as well as your cumulative points so far.'
                '\n\n'
                f'You will complete {P.blocks_per_experiment * P.trials_per_block // 2} trials of this condition; you may take a break in between trials whenever you need.'
            ),
            VISION: (
                'You will be able to see the target and where you land,'
                '\n'
                'however you will not see how many points you gained/lost on the trial nor your cumulative points so far.'
                '\n\n'
                f'You will complete {P.blocks_per_experiment * P.trials_per_block // 2} trials of this condition; you may take a break in between trials whenever you need.'
            ),
        }

    # First function called at start of each block
    def block(self):
        self.goggles.write(OPEN)

        # get task condition for block
        if P.practicing:
            self.condition = 'practice'
        else:
            self.condition = self.conditions.pop(0)

        # for storing block earnings
        self.bank = 0

        instrux = '(PRACTICE BLOCK)\n' if P.practicing else '(TESTING BLOCK)\n'

        if not P.practicing:
            instrux += self.instructions[self.condition]

        instrux += '\n\nPress spacebar to begin the next block of trials.\nStart each trial by touching and holding your finger within the blue semicircle.'

        # Present instructions
        fill()
        message(text=instrux, location=P.screen_c, blit_txt=True)
        flip()

        # Wait for spacebar press to start running trials
        while True:
            # Monitor for any commands to quit, etc
            q = pump(True)
            _ = ui_request(queue=q)
            if key_pressed(SPACE):
                break

    # First function called immediately prior to each trial
    def trial_prep(self):
        self.goggles.write(OPEN)
        # determine circle positions
        self.positions = self.get_circle_placements()

        # this changes for each trial, so needs to be (re)defined here
        self.bs.add_boundaries(
            [
                CircleBoundary(
                    PENALTY,
                    self.positions[PENALTY],
                    self.target_circle_d / 2,
                ),
                CircleBoundary(
                    REWARD,
                    self.positions[REWARD],
                    self.target_circle_d / 2,
                ),
            ]
        )

        # practice trial have "no" timeout, but code is cleaner if made excessively long instead
        trial_timeout = (
            TIMEOUT_AFTER if not P.practicing else 30000
        )  # 30s when practicing

        # Defined event sequence within trial
        self.evm.add_event(RECTANGLE_ONSET, RECT_ONSET)
        self.evm.add_event(CIRCLE_ONSET, CIRC_ONSET, after=RECTANGLE_ONSET)
        self.evm.add_event(GO_SIGNAL, PREVIEW_WINDOW, after=CIRCLE_ONSET)
        self.evm.add_event(TRIAL_TIMEOUT, trial_timeout, after=GO_SIGNAL)

        # present fix
        self.draw_display(fix=True)

        # trial started by having participant contact start position
        at_start_pos = False

        while not at_start_pos:
            # Monitor for any commands to quit, etc
            q = pump(True)
            _ = ui_request(queue=q)

            # NOTE: touchscreens reports touches as left-clicks
            touch_events = get_clicks(queue=q)

            # Break on any touches within start boundary
            if touch_events:
                at_start_pos = self.bs.within_boundary(
                    label=START, p=touch_events[0]
                )

    # Main trial logic
    def trial(self):  # type: ignore[override]

        # When (dev) testing, blit mouse to start position
        if P.development_mode:
            mouse_pos(position=(P.screen_x // 2, P.screen_y))  # type: ignore[operator]

        # Draw stimuli as appropriate; admonish early movements
        while self.evm.before(GO_SIGNAL):
            # Fetch any input events since last loop
            q = pump(True)

            # Check for events of interest
            _ = ui_request(queue=q)
            touch_events = get_clicks(released=True, queue=q)
            if touch_events:
                self.evm.stop_clock()

                msg = message(
                    'Please wait for the tone before moving from the starting position.'
                )
                self.draw_display(
                    also=(msg, self.bs.boundaries[RECT].center),
                )

                smart_sleep(P.feedback_duration)  # type: ignore[attr-defined]

                # NOTE:
                # TrialException() reshuffles current trial into block trial deck.
                # This preserves trial counts and randomization.
                raise TrialException('Premptive movement')

            rect_visible, circles_visible = False, False

            # Draw appropriate stimuli at appropriate time
            if self.evm.after(RECTANGLE_ONSET) and not rect_visible:
                self.draw_display(rect=True)
                rect_visible = True  # don't do redundant redraws

            if (
                self.evm.after(CIRCLE_ONSET)
                and not P.practicing
                and not circles_visible
            ):
                self.draw_display(rect=True, circles=True)
                circles_visible = True

        #
        #   Response period
        #

        self.go_tone.play()
        tone_played_at = self.evm.trial_time_ms

        rt, mt, clicked_on, clicked_at, pay = None, None, None, None, None

        while rt is None and self.evm.before(TRIAL_TIMEOUT):
            q = pump(True)
            _ = ui_request(queue=q)

            touch_events = get_clicks(released=True, queue=q)

            if touch_events:
                rt = self.evm.trial_time_ms - tone_played_at  # type: ignore[operator]

                # conditionally close goggles at movement start
                if self.condition == REWARD:
                    self.goggles.write(CLOSE)

        while mt is None and self.evm.before(TRIAL_TIMEOUT):
            # q = pump(True)
            # _ = ui_request(queue=q)

            # log touched point, if any
            # FIX: having get_clicks() and listen_for_click() is needlessly confusing
            clicked_at, clicked_on = self.listen_for_click()

            if clicked_on is not None:
                mt = self.evm.trial_time_ms - rt - tone_played_at  # type: ignore[operator]

        #
        #   Feedback phase
        #

        clear()  # the display

        # determine payout
        pay = self.get_payout(clicked_on)
        self.bank += pay

        # Present condition appropriate feedback
        if clicked_on is not None:

            # only movement time provided on practice trials
            if self.condition == 'practice':
                text = f'Movement time was: {trunc(mt)} ms.'  # type: ignore[operation]

                self.draw_display(
                    rect=True,
                    also=(message(text), self.bs.boundaries[RECT].center),
                )

            elif self.condition == REWARD:

                smart_sleep(300)
                self.goggles.write(OPEN)

                # Display earnings

                msg = message(f'Trial payout: {pay}', blit_txt=False)
                self.draw_display(
                    rect=True,
                    also=(msg, self.bs.boundaries[RECT].center),
                )

                smart_sleep(P.feedback_duration)  # type: ignore[attr-defined]

                msg = message(f'Total points: {self.bank}')
                self.draw_display(
                    rect=True,
                    also=(msg, self.bs.boundaries[RECT].center),
                )

                smart_sleep(P.feedback_duration)  # type: ignore[attr-defined]

            # Open goggles immediately on touch (providing endpoint feedback)
            else:
                self.goggles.write(OPEN)

        # on failures to complete movement within timeframe
        else:
            msg = message('Trial timed-out!\nNo response was detected!')
            self.draw_display(
                rect=True,
                also=(msg, self.bs.boundaries[RECT].center),
            )

        smart_sleep(P.feedback_duration)  # type: ignore[attr-defined]

        # Gets aggregated in sqlite database
        return {
            'practicing': P.practicing,
            'block_num': P.block_number,
            'trial_num': P.trial_number,
            'feedback_condition': self.condition,
            'reward_side': self.reward_side,  # type: ignore[defined]
            'reward_x': self.positions[REWARD][0],
            'reward_y': self.positions[REWARD][1],
            'clicked_on': clicked_on if clicked_on is not None else NA,
            'clicked_x': clicked_at[0] if clicked_at is not None else NA,
            'clicked_y': clicked_at[1] if clicked_at is not None else NA,
            'reaction_time': rt,
            'movement_time': mt,
            'trial_earnings': pay,
            'block_earnings': self.bank,
        }

    # Called at end of each trial
    def trial_clean_up(self):
        # If last trial of reward block, present total earnings
        if self.condition == REWARD:
            if P.trial_number % P.trials_per_block == 0:
                clear()
                self.goggles.write(OPEN)

                fill()
                message(
                    text=f'End of block! You scored: {self.bank}.\nPress spacebar to continue.',
                    location=P.screen_c,
                    blit_txt=True,
                )
                flip()

                while True:
                    q = pump(True)
                    _ = ui_request(queue=q)
                    if key_pressed(SPACE, queue=q):
                        break

                clear()

    # Called once at experiment end; almost never needed, like here
    def clean_up(self):
        pass

    # TODO: this could/should have been a dict
    def get_payout(self, clicked_on=None):
        if clicked_on is None:
            return TIMEOUT_PAYOUT

        elif clicked_on == REWARD:
            return REWARD_PAYOUT

        elif clicked_on == PENALTY:
            return PENALTY_PAYOUT

        elif clicked_on == OVERLAP:
            return VENN_PAYOUT

        elif clicked_on == OUTSIDE:
            return 0

        else:
            return MISS_PAYOUT

    # Logic for deciding "which" surface they touched
    # Also returns touch coordinates
    def listen_for_click(self):
        clicks = get_clicks()
        clicked = None

        if len(clicks):
            clicked_reward = self.bs.within_boundary(REWARD, p=clicks[0])
            clicked_penalty = self.bs.within_boundary(PENALTY, p=clicks[0])
            clicked_rect = self.bs.within_boundary(RECT, p=clicks[0])

            if clicked_rect:
                if clicked_reward and not clicked_penalty:
                    clicked = REWARD

                elif clicked_penalty and not clicked_reward:
                    clicked = PENALTY

                elif clicked_reward and clicked_penalty:
                    clicked = OVERLAP

                else:
                    clicked = RECT

            else:
                clicked = OUTSIDE
        else:
            clicks = [[-1, -1]]

        return clicks[0], clicked

    # Does what it says
    def draw_display(
        self,
        fix: bool = False,
        rect: bool = False,
        circles: bool = False,
        # "also" will try to blit whatever you pass it, does not check if that is a good idea
        # Needs to be a tuple os (thing, xy)
        also=None,
    ):

        fill()

        if fix:
            blit(
                self.stimuli[START],
                location=self.bs.boundaries[START].center,
                registration=5,
            )

            blit(
                self.stimuli[FIX],
                location=self.bs.boundaries[RECT].center,
                registration=5,
            )

        if rect:
            blit(
                self.stimuli[RECT],
                location=self.bs.boundaries[RECT].center,
                registration=5,
            )

        if circles:
            blit(
                self.stimuli[PENALTY],
                location=self.positions[PENALTY],
                registration=5,
            )
            blit(
                self.stimuli[REWARD],
                location=self.positions[REWARD],
                registration=5,
            )

        if also:
            blit(also[0], location=also[1], registration=5)

        flip()

    # Randomly determine circle placements within rectangle
    def get_circle_placements(self):
        rad_px = self.target_circle_d / 2
        circle_offset = 0.5 * rad_px
        padd = self.thick * 2

        rect_p1 = [int(xy) for xy in self.bs.boundaries[RECT].p1]
        rect_p2 = [int(xy) for xy in self.bs.boundaries[RECT].p2]

        origin_x = randrange(
            start=int(rect_p1[0] + (1.5 * rad_px) + padd),
            stop=int(rect_p2[0] - (1.5 * rad_px) - padd),
        )
        origin_y = randrange(
            start=int(rect_p1[1] + rad_px + padd),
            stop=int(rect_p2[1] - rad_px - padd),
        )

        if self.reward_side == 'right':  # type: ignore[attr-defined]
            placements = {
                PENALTY: (origin_x - circle_offset, origin_y),
                REWARD: (origin_x + circle_offset, origin_y),
            }
        else:
            placements = {
                REWARD: (origin_x - circle_offset, origin_y),
                PENALTY: (origin_x + circle_offset, origin_y),
            }

        return placements
