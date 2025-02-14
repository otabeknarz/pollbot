import asyncio
import logging
import sys
from os import getenv

from aiogram import Bot, Dispatcher, html
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import (
    CommandStart,
    Filter,
    ChatMemberUpdatedFilter,
    IS_MEMBER,
    IS_NOT_MEMBER,
)
from aiogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
    ChatMemberOwner,
    ChatMember,
    ChatMemberUpdated,
)
import aiohttp

from dotenv import load_dotenv

load_dotenv()

TOKEN = getenv("BOT_TOKEN")
CHANNEL_ID = getenv("CHANNEL_ID")
BASE_URL = getenv("BASE_URL")


dp = Dispatcher()
bot = Bot(token=TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


class TextEqualsFilter(Filter):
    def __init__(self, texts: list):
        self.texts = texts

    async def __call__(self, message: Message) -> bool:
        return message.text in self.texts


async def create_or_update_user(
    user_id: int, full_name: str, username: str | None = None, choice: str | None = None
) -> bool:
    async with aiohttp.ClientSession() as session:
        user_response = await session.post(
            f"{BASE_URL}/create-user/",
            json={
                "id": str(user_id),
                "first_name": full_name,
                "username": username,
                "choice": choice,
            },
        )
        if user_response.status != 201:
            user_response_update = await session.post(
                f"{BASE_URL}/update-user-choice/",
                json={"id": str(user_id), "choice": choice},
            )
            if user_response_update.status != 200:
                logging.error(await user_response_update.json())
                logging.error(await user_response.json())
                return False


async def check_is_user_subscribed_the_channel(user_id: int) -> bool:
    status: ChatMemberOwner | ChatMember = await bot.get_chat_member(
        CHANNEL_ID, user_id
    )
    return status.status == "left"


async def get_stats():
    async with aiohttp.ClientSession() as session:
        stats: aiohttp.ClientResponse = await session.get(f"{BASE_URL}/stats/")
        stats: dict = await stats.json()
    return stats


async def get_polls_inline_button() -> InlineKeyboardMarkup:
    async with aiohttp.ClientSession() as session:
        polls: aiohttp.ClientResponse = await session.get(f"{BASE_URL}/get-polls/")
        polls: list = await polls.json()

    polls_inline_buttons: list[InlineKeyboardButton] = [
        InlineKeyboardButton(text=poll, callback_data=poll) for poll in polls
    ]
    return InlineKeyboardMarkup(
        inline_keyboard=[
            polls_inline_buttons[i : i + 3]
            for i in range(0, len(polls_inline_buttons), 3)
        ],
    )


@dp.message(CommandStart())
async def command_start_handler(message: Message) -> None:
    await message.answer(f"Hello, {html.bold(message.from_user.full_name)}!")


@dp.message(TextEqualsFilter(["send_poll", "/send_poll", "poll"]))
async def send_poll_to_channel(message: Message) -> None:
    stats: dict = await get_stats()
    counter = 0

    def update_counter():
        nonlocal counter
        counter += 1
        return counter

    stats_text = "📈 Сўровнома бўйча натижалар:\n\n" + "\n".join(
        [
            f"<strong>{update_counter()}. {label}:</strong>    {count}"
            for label, count in stats.items()
        ]
    )
    keyboard: InlineKeyboardMarkup = await get_polls_inline_button()
    await bot.send_message(CHANNEL_ID, stats_text, reply_markup=keyboard)
    await message.answer("Poll sent to the channel")


@dp.callback_query()
async def poll_query_handler(query: CallbackQuery) -> None:
    if await check_is_user_subscribed_the_channel(query.from_user.id):
        await query.answer(
            "Сўровномада иштирок этиш учун каналимизга обуна бўлган бўлишингиз керак!",
            show_alert=True,
        )
        return

    have_already_voted = await create_or_update_user(
        user_id=query.from_user.id,
        full_name=f"{query.from_user.first_name} {query.from_user.last_name if query.from_user.last_name else ''}",
        username=query.from_user.username,
        choice=query.data,
    )
    if have_already_voted is False:
        await query.answer(
            "❌ Сиз олдин бошқа мактабга овоз бергансиз!", show_alert=True
        )

    stats: dict = await get_stats()
    counter = 0

    def update_counter():
        nonlocal counter
        counter += 1
        return counter

    stats_text = "📈 Сўровнома бўйча натижалар:\n\n" + "\n".join(
        [
            f"<strong>{update_counter()}. {label}:</strong>    {count}"
            for label, count in stats.items()
        ]
    )

    old_keyboard = query.message.reply_markup

    try:
        await query.message.edit_text(stats_text, reply_markup=old_keyboard)
        await query.answer(
            f"✅ Сизнинг овозингиз қабул қилинди! Овозингиз тез орада пайдо бўлади!\nСизнинг овозингиз: {query.data}",
            show_alert=True,
        )
    except Exception as e:
        logging.error(e)


@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER >> IS_NOT_MEMBER))
async def chat_member_updated_handler(event: ChatMemberUpdated) -> None:
    user = event.old_chat_member.user
    await create_or_update_user(
        user_id=user.id,
        full_name=f"{user.first_name} {user.last_name if user.last_name else ''}",
        username=user.username,
        choice=None,
    )


async def main() -> None:
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        stream=sys.stdout,
    )
    asyncio.run(main())
