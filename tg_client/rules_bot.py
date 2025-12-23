from aiogram import Bot, Dispatcher, Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, BotCommand
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from typing import Callable, Optional
from web3 import AsyncWeb3
from config import MANAGER_TG_BOT_TOKEN, MANAGER_TG_BOT_IDS, RPC, CHAIN_NAMES, BANNED_PATH, SUPPLY_DATA_PATH
from utils import get_logger
import asyncio
import json

logger = get_logger("RULES_BOT")

ERC20_ABI = [{"constant":True,"inputs":[],"name":"decimals","outputs":[{"name":"","type":"uint8"}],"type":"function"}]


class AddRuleStates(StatesGroup):
    waiting_token_address = State()
    waiting_event_type = State()
    waiting_chain = State()
    waiting_direction = State()
    waiting_claim_address = State()
    waiting_from_address = State()
    waiting_to_address = State()
    waiting_supply_percent = State()
    waiting_ticker = State()
    waiting_supply = State()
    waiting_circ_supply = State()
    waiting_decimals = State()


class DeleteRuleStates(StatesGroup):
    waiting_token_address = State()
    waiting_event_type = State()


class UpdateTokenStates(StatesGroup):
    waiting_token_address = State()
    waiting_field = State()
    waiting_value = State()


class ShowRuleStates(StatesGroup):
    waiting_token_address = State()


class BanTokenStates(StatesGroup):
    waiting_token_address = State()


class UnbanTokenStates(StatesGroup):
    waiting_token_address = State()


def get_main_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="➕ Add Rule", callback_data="menu_add_rule"),
         InlineKeyboardButton(text="🗑 Delete Rule", callback_data="menu_delete_rule")],
        [InlineKeyboardButton(text="✏️ Update Token", callback_data="menu_update_token"),
         InlineKeyboardButton(text="📋 List Rules", callback_data="menu_list_rules")],
        [InlineKeyboardButton(text="🔍 Show Rule", callback_data="menu_show_rule")],
        [InlineKeyboardButton(text="🚫 Ban Token", callback_data="menu_ban_token"),
         InlineKeyboardButton(text="✅ Unban Token", callback_data="menu_unban_token")],
        [InlineKeyboardButton(text="📜 Banned List", callback_data="menu_banned_list")],
    ])


def get_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Cancel", callback_data="action_cancel")]
    ])


def get_back_to_menu_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🏠 Back to Menu", callback_data="action_menu")]
    ])


def get_skip_cancel_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⏭ Skip", callback_data="action_skip"),
         InlineKeyboardButton(text="Cancel", callback_data="action_cancel")]
    ])


class RulesBot:
    def __init__(
        self,
        rules_manager,
        update_callback: Callable,
        bot_token: str = MANAGER_TG_BOT_TOKEN,
        chat_ids: list = MANAGER_TG_BOT_IDS,
    ):
        self.rules_manager = rules_manager
        self.update_callback = update_callback
        self.bot_token = bot_token
        self.chat_ids = chat_ids
        self.enabled = bool(bot_token and chat_ids)
        
        if not self.enabled:
            logger.warning("Rules bot disabled (no API key configured)")
            return
        
        self.bot = Bot(token=bot_token)
        self.storage = MemoryStorage()
        self.dp = Dispatcher(storage=self.storage)
        self.router = Router()
        self._setup_handlers()
        self.dp.include_router(self.router)
        
        self.w3_providers = {
            chain: AsyncWeb3(AsyncWeb3.AsyncHTTPProvider(rpc))
            for chain, rpc in RPC.items() if chain != 'SOLANA'
        }

    async def _set_commands(self):
        commands = [
            BotCommand(command="add_rule", description="Add a new custom rule"),
            BotCommand(command="delete_rule", description="Delete an existing rule"),
            BotCommand(command="update_token", description="Update token data"),
            BotCommand(command="list_rules", description="List all rules"),
            BotCommand(command="show_rule", description="Show rule details"),
            BotCommand(command="ban_token", description="Ban a token contract"),
            BotCommand(command="unban_token", description="Unban a token contract"),
            BotCommand(command="banned_list", description="Show banned tokens"),
            BotCommand(command="cancel", description="Cancel current operation"),
            BotCommand(command="help", description="Show help"),
        ]
        await self.bot.set_my_commands(commands)

    def _load_banned_list(self) -> dict:
        try:
            with open(BANNED_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if isinstance(data, list):
                    return {}
                return data
        except (FileNotFoundError, json.JSONDecodeError):
            return {}

    def _save_banned_list(self, banned_dict: dict):
        with open(BANNED_PATH, 'w', encoding='utf-8') as f:
            json.dump(banned_dict, f, indent=4)

    def _add_to_banned(self, token_address: str) -> tuple:
        """Add token to banned list with full data. Returns (success, token_data_dict, chains_list)."""
        banned_dict = self._load_banned_list()
        if token_address in banned_dict:
            return False, {}, []
        
        token_info, chains = self._get_token_data_from_supply(token_address)
        banned_dict[token_address] = {
            "token_data": token_info,
            "chains": chains
        }
        self._save_banned_list(banned_dict)
        return True, token_info, chains

    def _remove_from_banned(self, token_address: str) -> bool:
        """Remove token from banned list and restore to token_data.json."""
        banned_dict = self._load_banned_list()
        if token_address not in banned_dict:
            return False
        
        banned_entry = banned_dict[token_address]
        token_info = banned_entry.get("token_data", {})
        chains = banned_entry.get("chains", [])
        
        if token_info and chains:
            self._restore_to_token_data(token_address, token_info, chains)
        
        del banned_dict[token_address]
        self._save_banned_list(banned_dict)
        return True

    def _is_banned(self, token_address: str) -> bool:
        banned_dict = self._load_banned_list()
        return token_address in banned_dict

    def _get_token_data_from_supply(self, token_address: str) -> tuple:
        """Get token data from token_data.json. Returns (token_info_dict, chains_list)."""
        try:
            with open(SUPPLY_DATA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list) or len(data) != 2:
                return {}, []
            
            timestamp, token_data = data
            token_info = {}
            chains = []
            
            for chain_name in token_data.keys():
                if token_address in token_data[chain_name]:
                    if not token_info:
                        token_info = token_data[chain_name][token_address].copy()
                    chains.append(chain_name)
            
            return token_info, chains
        except Exception as e:
            logger.error(f"Error getting token data: {e}")
            return {}, []

    def _remove_from_token_data(self, token_address: str) -> int:
        """Remove token from token_data.json across all chains. Returns count of removals."""
        try:
            with open(SUPPLY_DATA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list) or len(data) != 2:
                return 0
            
            timestamp, token_data = data
            removed_count = 0
            
            for chain_name in list(token_data.keys()):
                if token_address in token_data[chain_name]:
                    del token_data[chain_name][token_address]
                    removed_count += 1
                    logger.info(f"Removed {token_address} from {chain_name} in token_data.json")
            
            if removed_count > 0:
                with open(SUPPLY_DATA_PATH, 'w', encoding='utf-8') as f:
                    json.dump([timestamp, token_data], f, indent=4)
            
            return removed_count
        except Exception as e:
            logger.error(f"Error removing token from token_data.json: {e}")
            return 0

    def _restore_to_token_data(self, token_address: str, token_info: dict, chains: list) -> bool:
        """Restore token to token_data.json for specified chains."""
        try:
            with open(SUPPLY_DATA_PATH, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if not isinstance(data, list) or len(data) != 2:
                return False
            
            timestamp, token_data = data
            
            for chain_name in chains:
                if chain_name in token_data:
                    token_data[chain_name][token_address] = token_info.copy()
                    logger.info(f"Restored {token_address} to {chain_name} in token_data.json")
            
            with open(SUPPLY_DATA_PATH, 'w', encoding='utf-8') as f:
                json.dump([timestamp, token_data], f, indent=4)
            
            return True
        except Exception as e:
            logger.error(f"Error restoring token to token_data.json: {e}")
            return False

    async def _get_decimals(self, token_address: str, chain_name: str) -> Optional[int]:
        try:
            w3 = self.w3_providers.get(chain_name)
            if not w3:
                return None
            contract = w3.eth.contract(
                address=AsyncWeb3.to_checksum_address(token_address),
                abi=ERC20_ABI
            )
            return await contract.functions.decimals().call()
        except Exception as e:
            logger.error(f"Error getting decimals: {e}")
            return None

    def _setup_handlers(self):
        
        @self.router.message(Command("cancel"))
        async def cmd_cancel(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await message.answer("❌ Operation cancelled.", reply_markup=get_back_to_menu_keyboard())

        @self.router.callback_query(F.data == "action_cancel")
        async def callback_cancel(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await callback.message.delete()
            await callback.message.answer("👋 *Rules Manager Bot*\n\nSelect an action:", parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

        @self.router.callback_query(F.data == "action_menu")
        async def callback_menu(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await callback.message.edit_text("👋 *Rules Manager Bot*\n\nSelect an action:", parse_mode="Markdown", reply_markup=get_main_menu_keyboard())

        @self.router.message(Command("start"))
        async def cmd_start(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await message.answer(
                "� *Rules Manager Bot*\n\nSelect an action:",
                parse_mode="Markdown",
                reply_markup=get_main_menu_keyboard()
            )

        @self.router.message(Command("help"))
        async def cmd_help(message: Message):
            if str(message.chat.id) not in self.chat_ids:
                return
            text = (
                "*📋 Rules Bot Commands:*\n\n"
                "*Event Types:*\n"
                "• `mint` \\- Token minting\n"
                "• `burn` \\- Token burning\n"
                "• `transfer` \\- Token transfer\n"
                "• `claim` \\- Claim event \\(transfer from claim contract\\)"
            )
            await message.answer(text, parse_mode="MarkdownV2", reply_markup=get_back_to_menu_keyboard())

        # ===== MENU CALLBACKS =====
        @self.router.callback_query(F.data == "menu_add_rule")
        async def menu_add_rule(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await callback.message.edit_text("📝 *Add New Rule*\n\nEnter token address:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(AddRuleStates.waiting_token_address)

        @self.router.callback_query(F.data == "menu_delete_rule")
        async def menu_delete_rule(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await self._show_delete_tokens_page(callback.message, 0, edit=True)

        @self.router.callback_query(F.data.startswith("delpage_"))
        async def handle_delete_page(callback: CallbackQuery):
            page = int(callback.data.replace("delpage_", ""))
            await callback.answer()
            await self._show_delete_tokens_page(callback.message, page, edit=True)

        @self.router.callback_query(F.data.startswith("deltoken_"))
        async def handle_delete_token_select(callback: CallbackQuery, state: FSMContext):
            idx = int(callback.data.replace("deltoken_", ""))
            rules_list = self.rules_manager.get_all_rules_flat()
            
            if idx >= len(rules_list):
                await callback.answer("Token not found")
                return
            
            chain, token_address, token_data = rules_list[idx]
            await state.update_data(token_address=token_address, chain=chain)
            await callback.answer()
            
            event_rules = token_data.get("event_rules", {})
            ticker = token_data.get("token_data", {}).get("ticker", "???")
            
            buttons = []
            for event_type, rule in event_rules.items():
                custom_name = rule.get("custom_event_name")
                display_name = custom_name if custom_name else event_type
                buttons.append([InlineKeyboardButton(text=f"🗑 {display_name}", callback_data=f"del_{event_type}")])
            buttons.append([InlineKeyboardButton(text="🗑 Delete ALL rules", callback_data="del_ALL")])
            buttons.append([InlineKeyboardButton(text="◀️ Back", callback_data="menu_delete_rule")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text(
                f"🗑 <b>Delete Rule for {ticker}</b>\n\n"
                f"<code>{token_address}</code>\n\n"
                f"Select rule to delete:",
                parse_mode="HTML",
                reply_markup=keyboard
            )
            await state.set_state(DeleteRuleStates.waiting_event_type)

        @self.router.callback_query(F.data == "menu_update_token")
        async def menu_update_token(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await callback.message.edit_text("✏️ *Update Token Data*\n\nEnter token address:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(UpdateTokenStates.waiting_token_address)

        @self.router.callback_query(F.data == "menu_list_rules")
        async def menu_list_rules(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await self._show_rules_page(callback.message, 0, edit=True)

        @self.router.callback_query(F.data.startswith("rules_page_"))
        async def handle_rules_page(callback: CallbackQuery):
            page = int(callback.data.replace("rules_page_", ""))
            await callback.answer()
            await self._show_rules_page(callback.message, page, edit=True)

        @self.router.callback_query(F.data == "menu_show_rule")
        async def menu_show_rule(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await callback.message.edit_text("🔍 *Show Rule*\n\nEnter token address:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(ShowRuleStates.waiting_token_address)

        # ===== BANNED TOKENS =====
        @self.router.callback_query(F.data == "menu_ban_token")
        async def menu_ban_token(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await callback.message.edit_text("🚫 *Ban Token*\n\nEnter token address to ban:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(BanTokenStates.waiting_token_address)

        @self.router.callback_query(F.data == "menu_unban_token")
        async def menu_unban_token(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await self._show_banned_tokens_page(callback.message, 0, edit=True)

        @self.router.callback_query(F.data == "menu_banned_list")
        async def menu_banned_list(callback: CallbackQuery, state: FSMContext):
            await state.clear()
            await callback.answer()
            await self._show_banned_list(callback.message, edit=True)

        @self.router.callback_query(F.data.startswith("bannedpage_"))
        async def handle_banned_page(callback: CallbackQuery):
            page = int(callback.data.replace("bannedpage_", ""))
            await callback.answer()
            await self._show_banned_tokens_page(callback.message, page, edit=True)

        @self.router.callback_query(F.data.startswith("unban_"))
        async def handle_unban_token(callback: CallbackQuery, state: FSMContext):
            idx = int(callback.data.replace("unban_", ""))
            banned_dict = self._load_banned_list()
            banned_addresses = list(banned_dict.keys())
            
            if idx >= len(banned_addresses):
                await callback.answer("Token not found")
                return
            
            token_address = banned_addresses[idx]
            banned_entry = banned_dict.get(token_address, {})
            ticker = banned_entry.get("token_data", {}).get("ticker", "???")
            chains = banned_entry.get("chains", [])
            
            success = self._remove_from_banned(token_address)
            self.update_callback()
            await callback.answer()
            
            if success:
                await callback.message.edit_text(
                    f"✅ Token unbanned and restored:\n"
                    f"<b>{ticker.upper()}</b>\n"
                    f"<code>{token_address}</code>\n"
                    f"Restored to: {', '.join(chains) if chains else 'N/A'}",
                    parse_mode="HTML",
                    reply_markup=get_back_to_menu_keyboard()
                )
            else:
                await callback.message.edit_text("❌ Failed to unban token", reply_markup=get_back_to_menu_keyboard())

        @self.router.message(Command("ban_token"))
        async def cmd_ban_token(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await message.answer("🚫 *Ban Token*\n\nEnter token address to ban:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(BanTokenStates.waiting_token_address)

        @self.router.message(BanTokenStates.waiting_token_address)
        async def process_ban_token_address(message: Message, state: FSMContext):
            token_address = message.text.strip()
            try:
                token_address = AsyncWeb3.to_checksum_address(token_address)
            except:
                await message.answer("❌ Invalid address format. Enter a valid token address:", reply_markup=get_cancel_keyboard())
                return
            
            if self._is_banned(token_address):
                await message.answer(f"⚠️ Token already banned:\n`{token_address}`", parse_mode="Markdown", reply_markup=get_back_to_menu_keyboard())
                await state.clear()
                return
            
            success, token_info, chains = self._add_to_banned(token_address)
            removed_count = self._remove_from_token_data(token_address)
            self.update_callback()
            
            ticker = token_info.get("ticker", "???").upper()
            chains_str = ", ".join(chains) if chains else "N/A"
            
            await message.answer(
                f"✅ <b>Token Banned</b>\n\n"
                f"Ticker: <b>{ticker}</b>\n"
                f"Address: <code>{token_address}</code>\n"
                f"Removed from: {chains_str}",
                parse_mode="HTML",
                reply_markup=get_back_to_menu_keyboard()
            )
            await state.clear()

        @self.router.message(Command("unban_token"))
        async def cmd_unban_token(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await self._show_banned_tokens_page(message, 0, edit=False)

        @self.router.message(Command("banned_list"))
        async def cmd_banned_list(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await self._show_banned_list(message, edit=False)

        # ===== ADD RULE =====
        @self.router.message(Command("add_rule"))
        async def cmd_add_rule(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await message.answer("📝 *Add New Rule*\n\nEnter token address:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(AddRuleStates.waiting_token_address)

        @self.router.message(AddRuleStates.waiting_token_address)
        async def process_token_address(message: Message, state: FSMContext):
            token_address = message.text.strip()
            try:
                token_address = AsyncWeb3.to_checksum_address(token_address)
            except:
                await message.answer("❌ Invalid address format. Enter a valid token address:", reply_markup=get_cancel_keyboard())
                return
            await state.update_data(token_address=token_address)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🪙 Mint", callback_data="type_mint"),
                 InlineKeyboardButton(text="🔥 Burn", callback_data="type_burn")],
                [InlineKeyboardButton(text="📤 Transfer", callback_data="type_transfer"),
                 InlineKeyboardButton(text="🎁 Claim", callback_data="type_claim")],
                [InlineKeyboardButton(text="Cancel", callback_data="action_cancel")],
            ])
            await message.answer("Select event type:", reply_markup=keyboard)
            await state.set_state(AddRuleStates.waiting_event_type)

        @self.router.callback_query(AddRuleStates.waiting_event_type, F.data.startswith("type_"))
        async def process_event_type(callback: CallbackQuery, state: FSMContext):
            selected_type = callback.data.replace("type_", "")
            is_claim = selected_type == "claim"
            event_type = "transfer" if is_claim else selected_type
            custom_event_name = "claim" if is_claim else None
            
            await state.update_data(
                event_type=event_type,
                is_claim=is_claim,
                custom_event_name=custom_event_name
            )
            await callback.answer()
            
            chains = [c for c in CHAIN_NAMES if c != 'SOLANA']
            buttons = [[InlineKeyboardButton(text=chain, callback_data=f"chain_{chain}")] for chain in chains]
            buttons.append([InlineKeyboardButton(text="Cancel", callback_data="action_cancel")])
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await callback.message.edit_text("Select chain:", reply_markup=keyboard)
            await state.set_state(AddRuleStates.waiting_chain)

        @self.router.callback_query(AddRuleStates.waiting_chain, F.data.startswith("chain_"))
        async def process_chain(callback: CallbackQuery, state: FSMContext):
            chain = callback.data.replace("chain_", "")
            await state.update_data(chain=chain)
            await callback.answer()
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="📈 Long", callback_data="dir_long"),
                 InlineKeyboardButton(text="📉 Short", callback_data="dir_short")],
                [InlineKeyboardButton(text="Cancel", callback_data="action_cancel")],
            ])
            await callback.message.edit_text("Select trade direction:", reply_markup=keyboard)
            await state.set_state(AddRuleStates.waiting_direction)

        @self.router.callback_query(AddRuleStates.waiting_direction, F.data.startswith("dir_"))
        async def process_direction(callback: CallbackQuery, state: FSMContext):
            direction = callback.data.replace("dir_", "")
            await state.update_data(direction=direction)
            await callback.answer()
            
            data = await state.get_data()
            is_claim = data.get("is_claim", False)
            event_type = data.get("event_type")
            
            if is_claim:
                await callback.message.edit_text(
                    "Enter claim contract addresses (from filter):\n\n"
                    "_One address per line. Multiple addresses allowed._",
                    parse_mode="Markdown",
                    reply_markup=get_cancel_keyboard()
                )
                await state.set_state(AddRuleStates.waiting_claim_address)
            elif event_type == "transfer":
                await callback.message.edit_text(
                    "Enter 'from' address filter:\n\n"
                    "_One address per line. Multiple addresses allowed._",
                    parse_mode="Markdown",
                    reply_markup=get_skip_cancel_keyboard()
                )
                await state.set_state(AddRuleStates.waiting_from_address)
            else:
                await callback.message.edit_text(
                    "Enter supply percent threshold:\n\n"
                    "_Example: 10 for 10%, 1 for 1%_",
                    parse_mode="Markdown",
                    reply_markup=get_cancel_keyboard()
                )
                await state.set_state(AddRuleStates.waiting_supply_percent)

        @self.router.message(AddRuleStates.waiting_claim_address)
        async def process_claim_address(message: Message, state: FSMContext):
            lines = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
            addresses = []
            for addr in lines:
                try:
                    addr = AsyncWeb3.to_checksum_address(addr)
                except:
                    await message.answer(f"❌ Invalid address: `{addr}`\n\nEnter valid addresses (one per line):", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
                    return
                addresses.append(addr)
            await state.update_data(from_filter=addresses, to_filter=[])
            await message.answer(
                "Enter supply percent threshold:\n\n"
                "_Example: 10 for 10%, 1 for 1%_",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            await state.set_state(AddRuleStates.waiting_supply_percent)

        # Skip callback for from address
        @self.router.callback_query(AddRuleStates.waiting_from_address, F.data == "action_skip")
        async def skip_from_address(callback: CallbackQuery, state: FSMContext):
            await callback.answer()
            await state.update_data(from_filter=[])
            await callback.message.edit_text(
                "Enter 'to' address filter:\n\n"
                "_One address per line. Multiple addresses allowed._",
                parse_mode="Markdown",
                reply_markup=get_skip_cancel_keyboard()
            )
            await state.set_state(AddRuleStates.waiting_to_address)

        @self.router.message(AddRuleStates.waiting_from_address)
        async def process_from_address(message: Message, state: FSMContext):
            lines = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
            addresses = []
            for addr in lines:
                try: 
                    addr = AsyncWeb3.to_checksum_address(addr)
                except:
                    await message.answer(f"❌ Invalid address: `{addr}`\n\nEnter valid addresses (one per line):", parse_mode="Markdown", reply_markup=get_skip_cancel_keyboard())
                    return
                addresses.append(addr)
            await state.update_data(from_filter=addresses)
            await message.answer(
                "Enter 'to' address filter:\n\n"
                "_One address per line. Multiple addresses allowed._",
                parse_mode="Markdown",
                reply_markup=get_skip_cancel_keyboard()
            )
            await state.set_state(AddRuleStates.waiting_to_address)

        # Skip callback for to address
        @self.router.callback_query(AddRuleStates.waiting_to_address, F.data == "action_skip")
        async def skip_to_address(callback: CallbackQuery, state: FSMContext):
            await callback.answer()
            await state.update_data(to_filter=[])
            await callback.message.edit_text(
                "Enter supply percent threshold:\n\n"
                "_Example: 10 for 10%, 1 for 1%_",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            await state.set_state(AddRuleStates.waiting_supply_percent)

        @self.router.message(AddRuleStates.waiting_to_address)
        async def process_to_address(message: Message, state: FSMContext):
            lines = [line.strip() for line in message.text.strip().split("\n") if line.strip()]
            addresses = []
            for addr in lines:
                try: 
                    addr = AsyncWeb3.to_checksum_address(addr)
                except:
                    await message.answer(f"❌ Invalid address: `{addr}`\n\nEnter valid addresses (one per line):", parse_mode="Markdown", reply_markup=get_skip_cancel_keyboard())
                    return
                addresses.append(addr)
            await state.update_data(to_filter=addresses)
            await message.answer(
                "Enter supply percent threshold:\n\n"
                "_Example: 10 for 10%, 1 for 1%_",
                parse_mode="Markdown",
                reply_markup=get_cancel_keyboard()
            )
            await state.set_state(AddRuleStates.waiting_supply_percent)

        @self.router.message(AddRuleStates.waiting_supply_percent)
        async def process_supply_percent(message: Message, state: FSMContext):
            try:
                supply_percent_input = float(message.text.strip())
                if supply_percent_input <= 0 or supply_percent_input > 100:
                    await message.answer("❌ Supply percent must be between 1 and 100. Try again:", reply_markup=get_cancel_keyboard())
                    return
                supply_percent = supply_percent_input / 100  # Convert to decimal
                await state.update_data(supply_percent=supply_percent)
                
                data = await state.get_data()
                token_address = data["token_address"]
                chain = data["chain"]
                
                token_data = self.rules_manager.get_token_data(token_address)
                
                if token_data and token_data.get("decimals") is not None:
                    token_data["chain"] = chain
                    await state.update_data(token_data=token_data)
                    await self._finalize_rule(message, state)
                else:
                    await message.answer("Token not found in database. Enter ticker:", reply_markup=get_cancel_keyboard())
                    await state.set_state(AddRuleStates.waiting_ticker)
                    
            except ValueError:
                await message.answer("❌ Invalid number. Enter supply percent:", reply_markup=get_cancel_keyboard())

        @self.router.message(AddRuleStates.waiting_ticker)
        async def process_ticker(message: Message, state: FSMContext):
            ticker = message.text.strip().upper()
            await state.update_data(ticker=ticker)
            await message.answer("Enter total supply:", reply_markup=get_cancel_keyboard())
            await state.set_state(AddRuleStates.waiting_supply)

        @self.router.message(AddRuleStates.waiting_supply)
        async def process_supply(message: Message, state: FSMContext):
            try:
                supply = float(message.text.strip().replace(",", ""))
                await state.update_data(supply=supply)
                await message.answer("Enter circulating supply:", reply_markup=get_cancel_keyboard())
                await state.set_state(AddRuleStates.waiting_circ_supply)
            except ValueError:
                await message.answer("❌ Invalid number. Enter total supply:", reply_markup=get_cancel_keyboard())

        @self.router.message(AddRuleStates.waiting_circ_supply)
        async def process_circ_supply(message: Message, state: FSMContext):
            try:
                circ_supply = float(message.text.strip().replace(",", ""))
                await state.update_data(circ_supply=circ_supply)
                
                data = await state.get_data()
                chain = data["chain"]
                token_address = data["token_address"]
                
                await message.answer("⏳ Fetching decimals from RPC...")
                decimals = await self._get_decimals(token_address, chain)
                
                if decimals is None:
                    await message.answer("Failed to fetch decimals. Enter manually (e.g. 18):", reply_markup=get_cancel_keyboard())
                    await state.set_state(AddRuleStates.waiting_decimals)
                    return
                
                token_data = {
                    "ticker": data["ticker"],
                    "chain": chain,
                    "decimals": decimals,
                    "circulating_supply": circ_supply,
                    "supply": data["supply"],
                }
                await state.update_data(token_data=token_data)
                await self._finalize_rule(message, state)
            except ValueError:
                await message.answer("❌ Invalid number. Enter circulating supply:", reply_markup=get_cancel_keyboard())

        @self.router.message(AddRuleStates.waiting_decimals)
        async def process_decimals(message: Message, state: FSMContext):
            try:
                decimals = int(message.text.strip())
                data = await state.get_data()
                
                token_data = {
                    "ticker": data["ticker"],
                    "chain": data["chain"],
                    "decimals": decimals,
                    "circulating_supply": data["circ_supply"],
                    "supply": data["supply"],
                }
                await state.update_data(token_data=token_data)
                await self._finalize_rule(message, state)
            except ValueError:
                await message.answer("❌ Invalid number. Enter decimals:", reply_markup=get_cancel_keyboard())

        # ===== LIST RULES =====
        @self.router.message(Command("list_rules"))
        async def cmd_list_rules(message: Message):
            if str(message.chat.id) not in self.chat_ids:
                return
            await self._show_rules_page(message, 0, edit=False)

        # ===== SHOW RULE =====
        @self.router.message(Command("show_rule"))
        async def cmd_show_rule(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await message.answer("🔍 *Show Rule*\n\nEnter token address:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(ShowRuleStates.waiting_token_address)

        @self.router.message(ShowRuleStates.waiting_token_address)
        async def process_show_rule_address(message: Message, state: FSMContext):
            token_address = message.text.strip()
            try:
                token_address = AsyncWeb3.to_checksum_address(token_address)
            except:
                await message.answer("❌ Invalid address format. Enter a valid token address:", reply_markup=get_cancel_keyboard())
                return
            
            # Search across all chains
            found_chain = None
            found_rules = None
            for chain, addr, data in self.rules_manager.get_all_rules_flat():
                if addr == token_address:
                    found_chain = chain
                    found_rules = data
                    break
            
            if not found_rules:
                await message.answer(f"❌ No rules found for `{token_address}`", parse_mode="Markdown", reply_markup=get_back_to_menu_keyboard())
                await state.clear()
                return
            
            token_data = found_rules.get("token_data", {})
            event_rules = found_rules.get("event_rules", {})
            
            text = f"*📊 Rules for {token_data.get('ticker', '???')}*\n\n"
            text += f"Address: `{token_address}`\n\n"
            text += f"*Token Data:*\n"
            text += f"  Chain: `{found_chain}`\n"
            text += f"  Decimals: `{token_data.get('decimals')}`\n"
            text += f"  Total Supply: `{token_data.get('supply')}`\n"
            text += f"  Circ Supply: `{token_data.get('circulating_supply')}`\n\n"
            
            text += f"*Event Rules:*\n"
            for event_type, rule in event_rules.items():
                custom_name = rule.get("custom_event_name")
                display_name = custom_name if custom_name else event_type
                supply_pct = rule.get('supply_percent', 0)
                supply_pct_display = f"{supply_pct * 100:.2f}%" if supply_pct else "N/A"
                text += f"\n  *{display_name}* (type: {event_type})\n"
                text += f"    Direction: `{rule.get('direction')}`\n"
                text += f"    Supply %: `{supply_pct_display}`\n"
                from_filter = rule.get('from', [])
                to_filter = rule.get('to', [])
                if from_filter:
                    if isinstance(from_filter, list):
                        for addr in from_filter:
                            text += f"    From: `{addr}`\n"
                    else:
                        text += f"    From: `{from_filter}`\n"
                if to_filter:
                    if isinstance(to_filter, list):
                        for addr in to_filter:
                            text += f"    To: `{addr}`\n"
                    else:
                        text += f"    To: `{to_filter}`\n"
            
            await message.answer(text, parse_mode="Markdown", reply_markup=get_back_to_menu_keyboard())
            await state.clear()

        # ===== DELETE RULE =====
        @self.router.message(Command("delete_rule"))
        async def cmd_delete_rule(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await message.answer("🗑 *Delete Rule*\n\nEnter token address:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(DeleteRuleStates.waiting_token_address)

        @self.router.message(DeleteRuleStates.waiting_token_address)
        async def process_delete_address(message: Message, state: FSMContext):
            token_address = message.text.strip()
            try:
                token_address = AsyncWeb3.to_checksum_address(token_address)
            except:
                await message.answer("❌ Invalid address format. Enter a valid token address:", reply_markup=get_cancel_keyboard())
                return
            
            # Search across all chains
            found_chain = None
            found_rules = None
            for chain, addr, data in self.rules_manager.get_all_rules_flat():
                if addr == token_address:
                    found_chain = chain
                    found_rules = data
                    break
            
            if not found_rules:
                await message.answer("❌ No rules found for this address.", reply_markup=get_back_to_menu_keyboard())
                await state.clear()
                return
            
            await state.update_data(token_address=token_address, chain=found_chain)
            event_rules = found_rules.get("event_rules", {})
            
            buttons = []
            for event_type, rule in event_rules.items():
                custom_name = rule.get("custom_event_name")
                display_name = custom_name if custom_name else event_type
                buttons.append([InlineKeyboardButton(text=f"🗑 {display_name}", callback_data=f"del_{event_type}")])
            buttons.append([InlineKeyboardButton(text="🗑 Delete ALL rules", callback_data="del_ALL")])
            buttons.append([InlineKeyboardButton(text="Cancel", callback_data="action_cancel")])
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
            await message.answer("Select rule to delete:", reply_markup=keyboard)
            await state.set_state(DeleteRuleStates.waiting_event_type)

        @self.router.callback_query(DeleteRuleStates.waiting_event_type, F.data.startswith("del_"))
        async def process_delete_type(callback: CallbackQuery, state: FSMContext):
            event_type = callback.data.replace("del_", "")
            data = await state.get_data()
            token_address = data["token_address"]
            chain = data["chain"]
            
            await callback.answer()
            
            if event_type == "ALL":
                success = self.rules_manager.remove_token(chain, token_address)
                if success:
                    self.update_callback()
                    await callback.message.edit_text(f"✅ Deleted all rules for\n<code>{token_address}</code> on {chain}", parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
                else:
                    await callback.message.edit_text("❌ Failed to delete rules", reply_markup=get_back_to_menu_keyboard())
            else:
                success = self.rules_manager.remove_rule(chain, token_address, event_type)
                if success:
                    self.update_callback()
                    await callback.message.edit_text(f"✅ Deleted {event_type} rule for\n<code>{token_address}</code> on {chain}", parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
                else:
                    await callback.message.edit_text("❌ Failed to delete rule", reply_markup=get_back_to_menu_keyboard())
            
            await state.clear()

        # ===== UPDATE TOKEN =====
        @self.router.message(Command("update_token"))
        async def cmd_update_token(message: Message, state: FSMContext):
            if str(message.chat.id) not in self.chat_ids:
                return
            await state.clear()
            await message.answer("✏️ *Update Token Data*\n\nEnter token address:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(UpdateTokenStates.waiting_token_address)

        @self.router.message(UpdateTokenStates.waiting_token_address)
        async def process_update_address(message: Message, state: FSMContext):
            token_address = message.text.strip()
            try:
                token_address = AsyncWeb3.to_checksum_address(token_address)
            except:
                await message.answer("❌ Invalid address format. Enter a valid token address:", reply_markup=get_cancel_keyboard())
                return
            
            # Search across all chains
            found_chain = None
            for chain, addr, data in self.rules_manager.get_all_rules_flat():
                if addr == token_address:
                    found_chain = chain
                    break
            
            if not found_chain:
                await message.answer("❌ No rules found for this address.", reply_markup=get_back_to_menu_keyboard())
                await state.clear()
                return
            
            await state.update_data(token_address=token_address, chain=found_chain)
            
            keyboard = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="Ticker", callback_data="field_ticker")],
                [InlineKeyboardButton(text="Total Supply", callback_data="field_supply")],
                [InlineKeyboardButton(text="Circulating Supply", callback_data="field_circulating_supply")],
                [InlineKeyboardButton(text="Decimals", callback_data="field_decimals")],
                [InlineKeyboardButton(text="Cancel", callback_data="action_cancel")],
            ])
            await message.answer("Select field to update:", reply_markup=keyboard)
            await state.set_state(UpdateTokenStates.waiting_field)

        @self.router.callback_query(UpdateTokenStates.waiting_field, F.data.startswith("field_"))
        async def process_update_field(callback: CallbackQuery, state: FSMContext):
            field = callback.data.replace("field_", "")
            await state.update_data(field=field)
            await callback.answer()
            await callback.message.edit_text(f"Enter new value for *{field}*:", parse_mode="Markdown", reply_markup=get_cancel_keyboard())
            await state.set_state(UpdateTokenStates.waiting_value)

        @self.router.message(UpdateTokenStates.waiting_value)
        async def process_update_value(message: Message, state: FSMContext):
            data = await state.get_data()
            token_address = data["token_address"]
            chain = data["chain"]
            field = data["field"]
            value = message.text.strip()
            
            if field in ["supply", "circulating_supply"]:
                try:
                    value = float(value.replace(",", ""))
                except ValueError:
                    await message.answer("❌ Invalid number. Try again:", reply_markup=get_cancel_keyboard())
                    return
            elif field == "decimals":
                try:
                    value = int(value)
                except ValueError:
                    await message.answer("❌ Invalid number. Try again:", reply_markup=get_cancel_keyboard())
                    return
            elif field == "ticker":
                value = value.upper()
            
            success = self.rules_manager.update_token_data(chain, token_address, field, value)
            
            if success:
                self.update_callback()
                await message.answer(f"✅ Updated *{field}* to `{value}`", parse_mode="Markdown", reply_markup=get_back_to_menu_keyboard())
            else:
                await message.answer("❌ Failed to update", reply_markup=get_back_to_menu_keyboard())
            
            await state.clear()

    def _escape_md(self, text: str) -> str:
        """Escape special Markdown characters."""
        chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
        for char in chars:
            text = text.replace(char, f'\\{char}')
        return text

    async def _show_rules_page(self, message: Message, page: int, edit: bool = False):
        rules_list = self.rules_manager.get_all_rules_flat()
        if not rules_list:
            if edit:
                await message.edit_text("📭 No custom rules configured.", reply_markup=get_back_to_menu_keyboard())
            else:
                await message.answer("📭 No custom rules configured.", reply_markup=get_back_to_menu_keyboard())
            return
        
        total_rules = len(rules_list)
        per_page = 10
        total_pages = (total_rules + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * per_page
        end_idx = min(start_idx + per_page, total_rules)
        page_rules = rules_list[start_idx:end_idx]
        
        text = f"📋 <b>Custom Rules</b> (Page {page + 1}/{total_pages})\n\n"
        for chain, addr, data in page_rules:
            ticker = data.get("token_data", {}).get("ticker", "???")
            event_rules = data.get("event_rules", {})
            
            events_text = []
            for evt, rule in event_rules.items():
                custom_name = rule.get("custom_event_name")
                display_name = custom_name if custom_name else evt
                events_text.append(display_name)
            
            rules_list_str = ", ".join(events_text) if events_text else "none"
            text += f"• <b>{ticker}</b> ({chain})\n  <code>{addr}</code>\n  Events: {rules_list_str}\n\n"
        
        buttons = []
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"rules_page_{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"rules_page_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton(text="🏠 Back to Menu", callback_data="action_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _show_delete_tokens_page(self, message: Message, page: int, edit: bool = False):
        rules_list = self.rules_manager.get_all_rules_flat()
        if not rules_list:
            if edit:
                await message.edit_text("📭 No custom rules to delete.", reply_markup=get_back_to_menu_keyboard())
            else:
                await message.answer("📭 No custom rules to delete.", reply_markup=get_back_to_menu_keyboard())
            return
        
        total_rules = len(rules_list)
        per_page = 5
        total_pages = (total_rules + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * per_page
        end_idx = min(start_idx + per_page, total_rules)
        page_rules = rules_list[start_idx:end_idx]
        
        text = f"🗑 <b>Delete Rule</b> (Page {page + 1}/{total_pages})\n\n"
        
        buttons = []
        for i, (chain, addr, data) in enumerate(page_rules):
            ticker = data.get("token_data", {}).get("ticker", "???")
            event_rules = data.get("event_rules", {})
            
            events_text = []
            for evt, rule in event_rules.items():
                custom_name = rule.get("custom_event_name")
                display_name = custom_name if custom_name else evt
                events_text.append(display_name)
            
            rules_list_str = ", ".join(events_text) if events_text else "none"
            text += f"{i + 1}. <b>{ticker}</b> ({chain})\n   <code>{addr}</code>\n   Events: {rules_list_str}\n\n"
            
            global_idx = start_idx + i
            buttons.append([InlineKeyboardButton(text=f"{i + 1}. {ticker} ({chain})", callback_data=f"deltoken_{global_idx}")])
        
        text += "Select token to delete:"
        
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"delpage_{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"delpage_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton(text="🏠 Back to Menu", callback_data="action_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _show_banned_tokens_page(self, message: Message, page: int, edit: bool = False):
        """Show paginated list of banned tokens with unban buttons."""
        banned_dict = self._load_banned_list()
        if not banned_dict:
            if edit:
                await message.edit_text("📭 No banned tokens.", reply_markup=get_back_to_menu_keyboard())
            else:
                await message.answer("📭 No banned tokens.", reply_markup=get_back_to_menu_keyboard())
            return
        
        banned_items = list(banned_dict.items())
        total_tokens = len(banned_items)
        per_page = 5
        total_pages = (total_tokens + per_page - 1) // per_page
        page = max(0, min(page, total_pages - 1))
        
        start_idx = page * per_page
        end_idx = min(start_idx + per_page, total_tokens)
        page_items = banned_items[start_idx:end_idx]
        
        text = f"🚫 <b>Unban Token</b> (Page {page + 1}/{total_pages})\n\nSelect token to unban:\n\n"
        
        buttons = []
        for i, (addr, data) in enumerate(page_items):
            global_idx = start_idx + i
            ticker = data.get("token_data", {}).get("ticker", "???").upper()
            chains = data.get("chains", [])
            chains_str = ", ".join(chains) if chains else "N/A"
            text += f"{i + 1}. <b>{ticker}</b> ({chains_str})\n   <code>{addr}</code>\n\n"
            buttons.append([InlineKeyboardButton(text=f"✅ Unban {ticker}", callback_data=f"unban_{global_idx}")])
        
        nav_row = []
        if page > 0:
            nav_row.append(InlineKeyboardButton(text="◀️ Prev", callback_data=f"bannedpage_{page - 1}"))
        if page < total_pages - 1:
            nav_row.append(InlineKeyboardButton(text="Next ▶️", callback_data=f"bannedpage_{page + 1}"))
        if nav_row:
            buttons.append(nav_row)
        buttons.append([InlineKeyboardButton(text="🏠 Back to Menu", callback_data="action_menu")])
        
        keyboard = InlineKeyboardMarkup(inline_keyboard=buttons)
        
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=keyboard)
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=keyboard)

    async def _show_banned_list(self, message: Message, edit: bool = False):
        """Show simple list of all banned tokens."""
        banned_dict = self._load_banned_list()
        if not banned_dict:
            if edit:
                await message.edit_text("📭 No banned tokens.", reply_markup=get_back_to_menu_keyboard())
            else:
                await message.answer("📭 No banned tokens.", reply_markup=get_back_to_menu_keyboard())
            return
        
        text = f"📜 <b>Banned Tokens</b> ({len(banned_dict)} total)\n\n"
        for i, (addr, data) in enumerate(banned_dict.items(), 1):
            ticker = data.get("token_data", {}).get("ticker", "???").upper()
            chains = data.get("chains", [])
            chains_str = ", ".join(chains) if chains else "N/A"
            text += f"{i}. <b>{ticker}</b> ({chains_str})\n   <code>{addr}</code>\n\n"
        
        if edit:
            await message.edit_text(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())
        else:
            await message.answer(text, parse_mode="HTML", reply_markup=get_back_to_menu_keyboard())

    async def _finalize_rule(self, message: Message, state: FSMContext):
        data = await state.get_data()
        
        token_address = data["token_address"]
        token_data = data["token_data"]
        event_type = data["event_type"]
        is_claim = data.get("is_claim", False)
        
        rule = {
            "direction": data["direction"],
            "custom_event_name": "claim" if is_claim else None,
            "from": data.get("from_filter"),
            "to": data.get("to_filter"),
            "supply_percent": data["supply_percent"],
        }
        
        self.rules_manager.add_rule(token_data.get('chain'), token_address, token_data, event_type, rule)
        self.update_callback()
        
        display_type = "claim" if is_claim else event_type
        supply_pct_display = f"{rule['supply_percent'] * 100:.2f}%"
        await message.answer(
            f"✅ *Rule Added!*\n\n"
            f"Token: `{token_data.get('ticker')}`\n"
            f"Chain: `{token_data.get('chain')}`\n"
            f"Event: `{display_type}`\n"
            f"Direction: `{rule['direction']}`\n"
            f"Supply %: `{supply_pct_display}`",
            parse_mode="Markdown",
            reply_markup=get_back_to_menu_keyboard()
        )
        await state.clear()

    async def start(self):
        if not self.enabled:
            return
        await self._set_commands()
        logger.info("Starting Rules Bot polling...")
        await self.dp.start_polling(self.bot)

    async def stop(self):
        if not self.enabled:
            return
        await self.dp.stop_polling()
        await self.bot.session.close()
