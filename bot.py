import os
import json
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands

def _parse_reaction_emoji(s):
    if not s:
        return None
    try:
        return discord.PartialEmoji.from_str(s)
    except Exception:
        return s

def _find_forum(guild: discord.Guild, name: str, category_name: str | None):
    target_cat_id = None
    if category_name:
        cat = discord.utils.get(guild.categories, name=category_name)
        target_cat_id = getattr(cat, 'id', None)
    for ch in guild.channels:
        if isinstance(ch, discord.ForumChannel) and ch.name == name:
            if (target_cat_id is None and ch.category is None) or (ch.category and ch.category.id == target_cat_id):
                return ch
    return None

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = os.getenv('OWNER_ID')

intents = discord.Intents.default()
intents.guilds = True
enable_members = os.getenv('ENABLE_MEMBERS_INTENT', '0').lower() in ('1', 'true', 'yes')
intents.members = bool(enable_members)
intents.message_content = False

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backup')
ROLE_FILE = os.path.join(BACKUP_DIR, 'roles.json')
TEXT_FILE = os.path.join(BACKUP_DIR, 'text_channels.json')
VOICE_FILE = os.path.join(BACKUP_DIR, 'voice_channels.json')
FORUM_FILE = os.path.join(BACKUP_DIR, 'forum_channels.json')
CATEGORY_FILE = os.path.join(BACKUP_DIR, 'categories.json')

os.makedirs(BACKUP_DIR, exist_ok=True)

def guild_only_and_owner():
    def predicate(ctx):
        if not ctx.guild:
            return False
        if OWNER_ID:
            try:
                return str(ctx.author.id) == str(OWNER_ID)
            except Exception:
                return False
        return True
    return commands.check(predicate)

def app_guild_only_and_owner():
    async def predicate(interaction: discord.Interaction):
        if interaction.guild is None:
            return False
        if OWNER_ID:
            try:
                return str(interaction.user.id) == str(OWNER_ID)
            except Exception:
                return False
        return True
    return app_commands.check(predicate)

@bot.event
async def on_ready():
    try:
        guild_id = os.getenv('GUILD_ID')
        if guild_id:
            guild = discord.Object(id=int(guild_id))
            await bot.tree.sync(guild=guild)
        else:
            await bot.tree.sync()
        print(f'Logged in as {bot.user} (ID: {bot.user.id}). Slash commands synced.')
    except Exception as e:
        print(f'Failed to sync slash commands: {e}')

@bot.tree.command(
    name='backup',
    description='サーバーのロール・チャンネル構成をバックアップします。',
    guild=discord.Object(id=int(os.getenv('GUILD_ID'))) if os.getenv('GUILD_ID') else None,
)
@app_guild_only_and_owner()
async def backup_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async def _progress(msg: str):
        try:
            await interaction.edit_original_response(content=msg)
        except Exception:
            try:
                await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass

    await _progress('🔄 バックアップ開始…')

    guild = interaction.guild

    await _progress('🧩 ロールをバックアップ中…')
    roles = []
    for role in guild.roles:
        if role.is_default():
            continue
        roles.append({
            'name': role.name,
            'color': role.color.value,
            'hoist': role.hoist,
            'mentionable': role.mentionable,
            'permissions': role.permissions.value,
            'position': role.position,
        })
    with open(ROLE_FILE, 'w', encoding='utf-8') as f:
        json.dump(roles, f, ensure_ascii=False, indent=2)
    await _progress(f'✅ ロール {len(roles)} 件を保存。次：カテゴリ…')

    await _progress('📁 カテゴリをバックアップ中…')

    categories = []
    for cat in guild.categories:
        overwrites = {}
        for target, perm in cat.overwrites.items():
            if isinstance(target, discord.Role):
                key = target.name
                ttype = 'role'
            else:
                key = str(target.id)
                ttype = 'member'
            allow = perm.pair()[0].value
            deny = perm.pair()[1].value
            overwrites[key] = {
                'target_type': ttype,
                'allow': allow,
                'deny': deny,
            }
        categories.append({
            'name': cat.name,
            'position': cat.position,
            'overwrites': overwrites,
        })
    with open(CATEGORY_FILE, 'w', encoding='utf-8') as f:
        json.dump(categories, f, ensure_ascii=False, indent=2)

    await _progress(f'✅ カテゴリ {len(categories)} 件を保存。次：テキストチャンネル…')

    await _progress('💬 テキストチャンネルをバックアップ中…')
    text_channels = []
    for ch in guild.text_channels:
        # 特殊板を除外
        if ch.name in ("moderator-only", "rules"):
            continue
        overwrites = {}
        for target, perm in ch.overwrites.items():
            key = None
            ttype = None
            if isinstance(target, discord.Role):
                key = target.name
                ttype = 'role'
            else:
                key = str(target.id)
                ttype = 'member'
            allow = perm.pair()[0].value
            deny = perm.pair()[1].value
            overwrites[key] = {
                'target_type': ttype,
                'allow': allow,
                'deny': deny,
            }
        text_channels.append({
            'name': ch.name,
            'category': ch.category.name if ch.category else None,
            'position': ch.position,
            'nsfw': ch.nsfw,
            'topic': ch.topic,
            'slowmode_delay': ch.slowmode_delay,
            'overwrites': overwrites,
        })
    with open(TEXT_FILE, 'w', encoding='utf-8') as f:
        json.dump(text_channels, f, ensure_ascii=False, indent=2)
    await _progress(f'✅ テキストチャンネル {len(text_channels)} 件を保存。次：フォーラム…')

    await _progress('📚 フォーラムをバックアップ中…')
    forum_channels = []
    for ch in guild.channels:
        if isinstance(ch, discord.ForumChannel):
            overwrites = {}
            for target, perm in ch.overwrites.items():
                if isinstance(target, discord.Role):
                    key = target.name
                    ttype = 'role'
                else:
                    key = str(getattr(target, 'id', target))
                    ttype = 'member'
                allow = perm.pair()[0].value
                deny = perm.pair()[1].value
                overwrites[key] = {
                    'target_type': ttype,
                    'allow': allow,
                    'deny': deny,
                }

            tags = []
            for t in getattr(ch, 'available_tags', []) or []:
                try:
                    emoji_str = str(t.emoji) if t.emoji else None
                except Exception:
                    emoji_str = None
                tags.append({
                    'name': t.name,
                    'emoji': emoji_str,
                    'moderated': getattr(t, 'moderated', False),
                })

            try:
                default_reaction = str(ch.default_reaction_emoji) if ch.default_reaction_emoji else None
            except Exception:
                default_reaction = None

            forum_channels.append({
                'name': ch.name,
                'category': ch.category.name if ch.category else None,
                'position': ch.position,
                'nsfw': ch.nsfw,
                'topic': getattr(ch, 'topic', None),
                'default_thread_slowmode_delay': getattr(ch, 'default_thread_slowmode_delay', None),
                'default_reaction_emoji': default_reaction,
                'default_layout': getattr(ch.default_layout, 'name', None) if getattr(ch, 'default_layout', None) else None,
                'default_sort_order': getattr(ch.default_sort_order, 'name', None) if getattr(ch, 'default_sort_order', None) else None,
                'overwrites': overwrites,
                'available_tags': tags,
            })
    with open(FORUM_FILE, 'w', encoding='utf-8') as f:
        json.dump(forum_channels, f, ensure_ascii=False, indent=2)
    await _progress(f'✅ フォーラム {len(forum_channels)} 件を保存。次：ボイスチャンネル…')

    await _progress('🔈 ボイスチャンネルをバックアップ中…')
    # Voice channels
    voice_channels = []
    for ch in guild.voice_channels:
        overwrites = {}
        for target, perm in ch.overwrites.items():
            if isinstance(target, discord.Role):
                key = target.name
                ttype = 'role'
            else:
                key = str(target.id)
                ttype = 'member'
            overwrites[key] = {
                'target_type': ttype,
                'allow': perm.pair()[0].value,
                'deny': perm.pair()[1].value,
            }
        voice_channels.append({
            'name': ch.name,
            'category': ch.category.name if ch.category else None,
            'position': ch.position,
            'bitrate': ch.bitrate,
            'user_limit': ch.user_limit,
            'overwrites': overwrites,
        })
    with open(VOICE_FILE, 'w', encoding='utf-8') as f:
        json.dump(voice_channels, f, ensure_ascii=False, indent=2)

    await _progress(f'🎉 バックアップ完了。ロール {len(roles)} 件・カテゴリ {len(categories)} 件・テキスト {len(text_channels)} 件・ボイス {len(voice_channels)} 件を保存しました。')
    # 追加でログを残したい場合は下記をコメント解除
    # await interaction.followup.send('バックアップ完了（詳細は上の進行メッセージ参照）', ephemeral=True)

@bot.tree.command(
    name='restore',
    description='バックアップからロール・チャンネル構成を復元します。',
    guild=discord.Object(id=int(os.getenv('GUILD_ID'))) if os.getenv('GUILD_ID') else None,
)
@app_guild_only_and_owner()
async def restore_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    async def _progress(msg: str):
        try:
            await interaction.edit_original_response(content=msg)
        except Exception:
            try:
                await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass

    await _progress('🔄 復元開始…')

    guild = interaction.guild
    role_map = {r.name: r for r in guild.roles}
    cat_map = {c.name: c for c in guild.categories}

    await _progress('🧩 ロールを復元中…')
    if os.path.exists(ROLE_FILE):
        with open(ROLE_FILE, 'r', encoding='utf-8') as f:
            stored_roles = json.load(f)
        # 高いpositionから順に処理（上から積む）
        for r in sorted(stored_roles, key=lambda x: x.get('position', 0), reverse=True):
            target_pos = int(r.get('position', 0))
            perms = discord.Permissions(r['permissions'])
            existing = discord.utils.get(guild.roles, name=r['name'])
            try:
                if existing:
                    try:
                        await existing.edit(permissions=perms, colour=discord.Colour(r['color']), hoist=r['hoist'], mentionable=r['mentionable'])
                    except Exception:
                        pass
                    try:
                        if existing.position != target_pos:
                            await existing.edit(position=target_pos)
                            await asyncio.sleep(0.15)
                    except Exception:
                        pass
                else:
                    created = await guild.create_role(
                        name=r['name'],
                        permissions=perms,
                        colour=discord.Colour(r['color']),
                        hoist=r['hoist'],
                        mentionable=r['mentionable']
                    )
                    try:
                        if created.position != target_pos:
                            await created.edit(position=target_pos)
                            await asyncio.sleep(0.15)
                    except Exception:
                        pass
            except Exception:
                pass
    else:
        stored_roles = []

    await _progress(f'✅ ロール {len(stored_roles) if os.path.exists(ROLE_FILE) else 0} 件を復元。次：カテゴリ…')

    await _progress('📁 カテゴリを復元中…')
    if os.path.exists(CATEGORY_FILE):
        with open(CATEGORY_FILE, 'r', encoding='utf-8') as f:
            stored_categories = json.load(f)
        stored_categories_sorted = sorted(stored_categories, key=lambda c: c.get('position', 0))
        for c in stored_categories_sorted:
            overwrites = {}
            for target_id, perm in c.get('overwrites', {}).items():
                if perm.get('target_type') == 'role':
                    target = role_map.get(target_id)
                else:
                    try:
                        target = guild.get_member(int(target_id)) or await guild.fetch_member(int(target_id))
                    except Exception:
                        target = None
                if target is None:
                    continue
                try:
                    allow_bits = int(perm.get('allow', 0))
                    deny_bits = int(perm.get('deny', 0))
                    allow_perm = discord.Permissions(allow_bits)
                    deny_perm = discord.Permissions(deny_bits)
                    ow = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)
                except Exception:
                    continue
                overwrites[target] = ow
            try:
                await guild.create_category(
                    c['name'],
                    position=c.get('position', None),
                    overwrites=dict(overwrites),
                )
            except Exception:
                pass
        cat_count = len(stored_categories)
    else:
        stored_categories = []
        cat_count = 0

    role_map = {r.name: r for r in guild.roles}
    cat_map = {c.name: c for c in guild.categories}

    await _progress(f'✅ カテゴリ {cat_count} 件を復元。次：テキストチャンネル…')

    await _progress('💬 テキストチャンネルを復元中…')
    if os.path.exists(TEXT_FILE):
        with open(TEXT_FILE, 'r', encoding='utf-8') as f:
            stored_text = json.load(f)
        for ch in stored_text:
            category = cat_map.get(ch['category']) if ch['category'] else None
            overwrites = {}
            for target_id, perm in ch.get('overwrites', {}).items():
                if perm.get('target_type') == 'role':
                    target = role_map.get(target_id)
                else:
                    try:
                        target = guild.get_member(int(target_id)) or await guild.fetch_member(int(target_id))
                    except Exception:
                        target = None
                if target is None:
                    continue
                try:
                    allow_bits = int(perm.get('allow', 0))
                    deny_bits = int(perm.get('deny', 0))
                    allow_perm = discord.Permissions(allow_bits)
                    deny_perm = discord.Permissions(deny_bits)
                    ow = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)
                except Exception:
                    continue
                overwrites[target] = ow
            new = await guild.create_text_channel(
                ch['name'],
                category=category,
                position=ch.get('position', None),
                nsfw=ch.get('nsfw', False),
                topic=ch.get('topic'),
                slowmode_delay=ch.get('slowmode_delay', 0),
                overwrites=dict(overwrites),
            )
    else:
        stored_text = []

    await _progress(f'✅ テキストチャンネル {len(stored_text) if os.path.exists(TEXT_FILE) else 0} 件を復元。次：フォーラム…')

    await _progress('📚 フォーラムを復元中…')
    if os.path.exists(FORUM_FILE):
        with open(FORUM_FILE, 'r', encoding='utf-8') as f:
            stored_forum = json.load(f)
        for ch in stored_forum:
            category = cat_map.get(ch['category']) if ch.get('category') else None
            if category is None and ch.get('category'):
                category = discord.utils.get(guild.categories, name=ch.get('category'))

            overwrites = {}
            for target_id, perm in (ch.get('overwrites') or {}).items():
                if perm.get('target_type') == 'role':
                    target = role_map.get(target_id)
                else:
                    try:
                        target = guild.get_member(int(target_id)) or None
                    except Exception:
                        target = None
                if target is None:
                    continue
                try:
                    allow_bits = int(perm.get('allow', 0))
                    deny_bits = int(perm.get('deny', 0))
                    allow_perm = discord.Permissions(allow_bits)
                    deny_perm = discord.Permissions(deny_bits)
                    ow = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)
                    overwrites[target] = ow
                except Exception:
                    continue

            tag_objs = []
            for t in (ch.get('available_tags') or []):
                try:
                    emoji_val = _parse_reaction_emoji(t.get('emoji')) if t.get('emoji') else None
                    tag_objs.append(discord.ForumTag(name=t.get('name'), emoji=emoji_val, moderated=bool(t.get('moderated', False))))
                except Exception:
                    pass

            default_reaction = _parse_reaction_emoji(ch.get('default_reaction_emoji'))

            existed = _find_forum(guild, ch['name'], ch.get('category'))

            create_forum_func = getattr(guild, 'create_forum', None) or getattr(guild, 'create_forum_channel', None)

            kwargs = dict(
                category=category,
                position=ch.get('position', None),
                nsfw=ch.get('nsfw', False),
                topic=ch.get('topic'),
                default_thread_slowmode_delay=ch.get('default_thread_slowmode_delay'),
                default_reaction_emoji=default_reaction,
                available_tags=tag_objs or None,
                overwrites=dict(overwrites),
            )

            if hasattr(discord, 'ForumLayout') and ch.get('default_layout'):
                try:
                    kwargs['default_layout'] = getattr(discord.ForumLayout, ch['default_layout'])
                except Exception:
                    pass
            if hasattr(discord, 'SortOrder') and ch.get('default_sort_order'):
                try:
                    kwargs['default_sort_order'] = getattr(discord.SortOrder, ch['default_sort_order'])
                except Exception:
                    pass

            try:
                if existed:
                    edit_kwargs = {k: v for k, v in kwargs.items() if k not in ('available_tags', 'default_layout', 'default_sort_order')}
                    try:
                        await existed.edit(**edit_kwargs)
                    except Exception:
                        pass
                    if tag_objs:
                        try:
                            await existed.set_available_tags(tag_objs)
                        except Exception:
                            pass
                else:
                    if create_forum_func is not None:
                        await create_forum_func(ch['name'], **kwargs)
            except Exception:
                pass
    else:
        stored_forum = []

    await _progress(f'✅ フォーラム {len(stored_forum) if os.path.exists(FORUM_FILE) else 0} 件を復元。次：ボイスチャンネル…')

    await _progress('🔈 ボイスチャンネルを復元中…')
    if os.path.exists(VOICE_FILE):
        with open(VOICE_FILE, 'r', encoding='utf-8') as f:
            stored_voice = json.load(f)
        for ch in stored_voice:
            category = cat_map.get(ch['category']) if ch['category'] else None
            overwrites = {}
            for target_id, perm in ch.get('overwrites', {}).items():
                if perm.get('target_type') == 'role':
                    target = role_map.get(target_id)
                else:
                    try:
                        target = guild.get_member(int(target_id)) or await guild.fetch_member(int(target_id))
                    except Exception:
                        target = None
                if target is None:
                    continue
                try:
                    allow_bits = int(perm.get('allow', 0))
                    deny_bits = int(perm.get('deny', 0))
                    allow_perm = discord.Permissions(allow_bits)
                    deny_perm = discord.Permissions(deny_bits)
                    ow = discord.PermissionOverwrite.from_pair(allow_perm, deny_perm)
                except Exception:
                    continue
                overwrites[target] = ow
            new = await guild.create_voice_channel(
                ch['name'],
                category=category,
                bitrate=ch.get('bitrate', None),
                user_limit=ch.get('user_limit', 0),
                overwrites=dict(overwrites),
            )
    else:
        stored_voice = []

    await _progress(
        f'🎉 復元完了。ロール {len(stored_roles) if os.path.exists(ROLE_FILE) else 0} 件・'
        f'カテゴリ {len(stored_categories) if os.path.exists(CATEGORY_FILE) else 0} 件・'
        f'テキスト {len(stored_text) if os.path.exists(TEXT_FILE) else 0} 件・'
        f'フォーラム {len(stored_forum) if os.path.exists(FORUM_FILE) else 0} 件・'
        f'ボイス {len(stored_voice) if os.path.exists(VOICE_FILE) else 0} 件を復元しました。'
    )

#TODO: デバック用　削除する
@bot.tree.command(
    name='nuke_all',
    description='⚠️ サーバー内のチャンネル/カテゴリ/ロールを一括削除します（現在のチャンネルは最後まで残します）。超危険。',
    guild=discord.Object(id=int(os.getenv('GUILD_ID'))) if os.getenv('GUILD_ID') else None,
)
@app_guild_only_and_owner()
async def nuke_all_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    guild = interaction.guild
    if guild is None:
        return await interaction.followup.send('ギルド内でのみ使用できます。', ephemeral=True)

    # 対象の収集（現在のチャンネルは最後まで残す）
    keep_channel = interaction.channel
    text_targets = [c for c in guild.text_channels if c.id != getattr(keep_channel, 'id', None)]
    forum_targets = [c for c in guild.channels if isinstance(c, discord.ForumChannel) and c.id != getattr(keep_channel, 'id', None)]
    voice_targets = [c for c in guild.voice_channels if c.id != getattr(keep_channel, 'id', None)]
    category_targets = list(guild.categories)
    role_targets = [r for r in guild.roles if (not r.is_default()) and (not r.managed)]  # @everyone と連携ロール除外(権限なしになるので)

    warning = (
        '⚠️ **超危険**: 次のリソースを削除します\n'
        f'- テキストチャンネル: {len(text_targets)}\n'
        f'- フォーラム: {len(forum_targets)}\n'
        f'- ボイスチャンネル: {len(voice_targets)}\n'
        f'- カテゴリ: {len(category_targets)}\n'
        f'- ロール: {len(role_targets)}（@everyone/連携ロール除く）\n\n'
        'この操作は取り消せません。バックアップを事前に実行してください。\n'
        '5秒後にボタンが有効になります。'
    )

    async def _edit(content=None, view=None):
        try:
            await interaction.edit_original_response(content=content, view=view)
        except Exception:
            try:
                if view is not None:
                    await interaction.followup.send(content or '\u200b', view=view, ephemeral=True)
                else:
                    await interaction.followup.send(content or '\u200b', ephemeral=True)
            except Exception:
                pass

    class ConfirmNukeView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=None)
            # 初期は無効化
            self.confirm_button.disabled = True
            # 5秒後に有効化
            asyncio.create_task(self.enable_later())

        async def enable_later(self):
            await asyncio.sleep(5)
            self.confirm_button.disabled = False
            await _edit(content=warning + '\n\n**削除する/やめる** を選んでください。', view=self)

        @discord.ui.button(label='削除する', style=discord.ButtonStyle.danger, custom_id='nuke_confirm')
        async def confirm_button(self, interaction_btn: discord.Interaction, button: discord.ui.Button):
            # 二重実行防止
            self.confirm_button.disabled = True
            self.cancel_button.disabled = True
            await _edit(content='🧨 一括削除を開始します…', view=self)

            # 進捗用ヘルパー
            async def progress(msg: str):
                await _edit(content=msg, view=self)

            deleted_text = 0
            for ch in list(text_targets):
                try:
                    await ch.delete(reason='nuke_all by owner')
                    deleted_text += 1
                    if deleted_text % 5 == 0:
                        await progress(f'🧹 テキストチャンネル削除中… {deleted_text}/{len(text_targets)}')
                except Exception:
                    pass
            await progress(f'✅ テキストチャンネル {deleted_text}/{len(text_targets)} 削除完了。次：フォーラム…')

            deleted_forum = 0
            for ch in list(forum_targets):
                try:
                    await ch.delete(reason='nuke_all by owner')
                    deleted_forum += 1
                    if deleted_forum % 5 == 0:
                        await progress(f'🧹 フォーラム削除中… {deleted_forum}/{len(forum_targets)}')
                except Exception:
                    pass
            await progress(f'✅ フォーラム {deleted_forum}/{len(forum_targets)} 削除完了。次：ボイスチャンネル…')

            deleted_voice = 0
            for ch in list(voice_targets):
                try:
                    await ch.delete(reason='nuke_all by owner')
                    deleted_voice += 1
                    if deleted_voice % 5 == 0:
                        await progress(f'🧹 ボイスチャンネル削除中… {deleted_voice}/{len(voice_targets)}')
                except Exception:
                    pass
            await progress(f'✅ ボイスチャンネル {deleted_voice}/{len(voice_targets)} 削除完了。次：カテゴリ…')

            deleted_cat = 0
            # カテゴリは後ろから消すと依存が少ない！
            for cat in list(sorted(category_targets, key=lambda c: c.position, reverse=True)):
                try:
                    await cat.delete(reason='nuke_all by owner')
                    deleted_cat += 1
                    if deleted_cat % 5 == 0:
                        await progress(f'🧹 カテゴリ削除中… {deleted_cat}/{len(category_targets)}')
                except Exception:
                    pass
            await progress(f'✅ カテゴリ {deleted_cat}/{len(category_targets)} 削除完了。次：ロール…')

            # ロール削除（Botの権限階層により失敗する場合あり）
            deleted_roles = 0
            for r in list(sorted(role_targets, key=lambda r: r.position)):
                try:
                    await r.delete(reason='nuke_all by owner')
                    deleted_roles += 1
                    if deleted_roles % 10 == 0:
                        await progress(f'🧹 ロール削除中… {deleted_roles}/{len(role_targets)}')
                except Exception:
                    pass
            await progress(f'✅ ロール {deleted_roles}/{len(role_targets)} 削除完了。')

            # 最後に現在のチャンネルを残す（ログや次操作のため）
            await _edit(content='🎉 一括削除が完了しました（このチャンネルは残しています）。', view=None)

        @discord.ui.button(label='やめる', style=discord.ButtonStyle.secondary, custom_id='nuke_cancel')
        async def cancel_button(self, interaction_btn: discord.Interaction, button: discord.ui.Button):
            self.confirm_button.disabled = True
            self.cancel_button.disabled = True
            await _edit(content='❎ キャンセルしました。', view=None)

    view = ConfirmNukeView()
    await _edit(content=warning, view=view)

if __name__ == '__main__':
    if not TOKEN:
        print('DISCORD_TOKEN が .env に設定されていません')
    else:
        if enable_members:
            print('WARNING: ENABLE_MEMBERS_INTENT is set. Make sure you enabled "Server Members Intent" in the Discord Developer Portal for this application.')
        try:
            bot.run(TOKEN)
        except discord.errors.PrivilegedIntentsRequired as e:
            print('起動に失敗しました: Privileged intents が有効になっていません。')
            print('Developer Portal のアプリ設定で "Server Members Intent" と/または "Message Content Intent" を有効化するか、')
            print('もしくは .env で ENABLE_MEMBERS_INTENT を無効にしてください。')
            raise
