from aiogram.fsm.state import State, StatesGroup


class ProposeGiveawayStates(StatesGroup):
    choose_type = State()
    enter_title = State()
    enter_content = State()
    enter_media = State()
    confirm = State()


class ProposeIdeaStates(StatesGroup):
    enter_text = State()


class AdminCreateGiveawayStates(StatesGroup):
    choose_type = State()
    choose_template = State()
    enter_title = State()
    enter_content = State()
    enter_media = State()
    enter_deadline = State()
    select_channels = State()
    confirm = State()


class AdminReworkStates(StatesGroup):
    enter_comment = State()


class AdminAddChannelStates(StatesGroup):
    enter_username = State()


class AdminAddGiftStates(StatesGroup):
    enter_name = State()
    enter_cost = State()
    choose_type = State()


class AdminWhitelistStates(StatesGroup):
    enter_user_id = State()


class AdminSearchUserStates(StatesGroup):
    enter_user_id = State()


class AdminBroadcastStates(StatesGroup):
    enter_message = State()
    confirm = State()


class TaskAnswerStates(StatesGroup):
    waiting_answer = State()
    waiting_step = State()


class SupportStates(StatesGroup):
    enter_message = State()


class WithdrawDesignStates(StatesGroup):
    choose_design = State()


class WithdrawStarsStates(StatesGroup):
    enter_amount = State()
