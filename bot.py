import os
import json
import asyncio
from dotenv import load_dotenv
import discord
from discord.ext import commands
from discord import app_commands
from datetime import datetime

load_dotenv()
TOKEN = os.getenv('DISCORD_TOKEN')
OWNER_ID = os.getenv('OWNER_ID')

intents = discord.Intents.default()
intents.guilds = True
enable_members = os.getenv('ENABLE_MEMBERS_INTENT', '0').lower() in ('1', 'true', 'yes')
intents.members = bool(enable_members)
enable_msg_content = os.getenv('ENABLE_MESSAGE_CONTENT_INTENT', '0').lower() in ('1', 'true', 'yes')
intents.message_content = bool(enable_msg_content)

bot = commands.Bot(command_prefix=commands.when_mentioned, intents=intents)

BACKUP_DIR = os.path.join(os.path.dirname(__file__), 'backup')
ROLE_FILE = os.path.join(BACKUP_DIR, 'roles.json')
TEXT_FILE = os.path.join(BACKUP_DIR, 'text_channels.json')
VOICE_FILE = os.path.join(BACKUP_DIR, 'voice_channels.json')
CATEGORY_FILE = os.path.join(BACKUP_DIR, 'categories.json')

os.makedirs(BACKUP_DIR, exist_ok=True)
CHAT_DIR = os.path.join(BACKUP_DIR, 'chat')
os.makedirs(CHAT_DIR, exist_ok=True)

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
    await _progress(f'✅ テキストチャンネル {len(text_channels)} 件を保存。次：ボイスチャンネル…')

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
    name='backup_chat',
    description='このチャンネルの直近メッセージを保存します（デフォルト100件）。',
    guild=discord.Object(id=int(os.getenv('GUILD_ID'))) if os.getenv('GUILD_ID') else None,
)
@app_guild_only_and_owner()
@app_commands.describe(count='保存する件数（既定: 100, 最大: 1000）')
async def backup_chat_slash(interaction: discord.Interaction, count: int = 100):
    await interaction.response.defer(ephemeral=True)

    # validate channel type
    channel = interaction.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return await interaction.followup.send('テキストチャンネル/スレッドで実行してください。', ephemeral=True)

    # Require Message Content intent for reliable content capture
    if not intents.message_content:
        return await interaction.followup.send(
            'メッセージ本文を取得できませんでした。`ENABLE_MESSAGE_CONTENT_INTENT=1` を .env に設定し、Developer Portal で **Message Content Intent** を有効化してください。',
            ephemeral=True,
        )

    count = max(1, min(int(count), 1000))

    async def _progress(msg: str):
        try:
            await interaction.edit_original_response(content=msg)
        except Exception:
            try:
                await interaction.followup.send(msg, ephemeral=True)
            except Exception:
                pass

    await _progress(f'💾 チャットのバックアップを開始… 取得件数: {count}')

    messages = []
    fetched = 0
    try:
        async for m in channel.history(limit=count, oldest_first=False):
            # attachments metadata only（URLは貼り付けで復元）
            atts = [{'filename': a.filename, 'url': a.url, 'content_type': a.content_type} for a in m.attachments]
            embeds = [e.to_dict() for e in m.embeds] if m.embeds else []
            stickers = [{'id': s.id, 'name': s.name, 'format_type': getattr(s, 'format', None)} for s in getattr(m, 'stickers', [])]
            reactions = [{'emoji': str(r.emoji), 'count': r.count} for r in m.reactions]

            # Prefer normal content; fall back to system_content when content is empty (join/pinなど)
            content_text = m.content if isinstance(getattr(m, 'content', None), str) else None
            if not content_text:
                content_text = getattr(m, 'system_content', None)

            messages.append({
                'id': m.id,
                'author_id': getattr(m.author, 'id', None),
                'author_name': getattr(m.author, 'display_name', getattr(m.author, 'name', None)),
                'content': content_text or '',
                'created_at': m.created_at.isoformat() if getattr(m, 'created_at', None) else None,
                'attachments': atts,
                'embeds': embeds,
                'stickers': stickers,
                'reactions': reactions,
                'reference': {
                    'message_id': getattr(m.reference, 'message_id', None) if getattr(m, 'reference', None) else None,
                    'channel_id': getattr(getattr(m, 'reference', None), 'channel_id', None),
                } if getattr(m, 'reference', None) else None,
                'type': int(getattr(m, 'type', 0)) if hasattr(m, 'type') else 0,
            })
            fetched += 1
            if fetched % 50 == 0:
                await _progress(f'📥 取得中… {fetched}/{count}')
    except discord.Forbidden:
        return await _progress('権限不足でメッセージを取得できませんでした。（Message Content Intent が必要な場合があります）')

    # 保存は古い順に
    messages.reverse()

    safe_name = channel.name if hasattr(channel, 'name') and channel.name else f'chan_{channel.id}'
    ts = datetime.utcnow().strftime('%Y%m%d-%H%M%S')
    filename = f"{safe_name}__{ts}.json"
    path = os.path.join(CHAT_DIR, filename)

    with open(path, 'w', encoding='utf-8') as f:
        json.dump({
            'channel_id': channel.id,
            'channel_name': safe_name,
            'saved_at': ts,
            'count': len(messages),
            'messages': messages,
        }, f, ensure_ascii=False, indent=2)

    await _progress(f'✅ チャットのバックアップ完了: backup/chat/{filename}（{len(messages)}件）')

@bot.tree.command(
    name='restore_chat',
    description='このチャンネル名と一致するチャットバックアップから復元します。',
    guild=discord.Object(id=int(os.getenv('GUILD_ID'))) if os.getenv('GUILD_ID') else None,
)
@app_guild_only_and_owner()
async def restore_chat_slash(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)

    channel = interaction.channel
    if not isinstance(channel, (discord.TextChannel, discord.Thread)):
        return await interaction.followup.send('テキストチャンネル/スレッドで実行してください。', ephemeral=True)

    safe_name = channel.name if hasattr(channel, 'name') and channel.name else f'chan_{channel.id}'

    # 候補の探索
    candidates = []
    for fn in sorted(os.listdir(CHAT_DIR)):
        if not fn.endswith('.json'):
            continue
        if fn.startswith(f"{safe_name}__") or fn == f"{safe_name}.json":
            full = os.path.join(CHAT_DIR, fn)
            try:
                stat = os.stat(full)
                candidates.append((fn, stat.st_mtime))
            except Exception:
                continue

    if not candidates:
        return await interaction.followup.send('このチャンネル名に一致するチャットバックアップが見つかりません。', ephemeral=True)

    # 新しい順に最大25件を選択肢に
    candidates.sort(key=lambda x: x[1], reverse=True)
    choices = candidates[:25]

    async def _edit(content=None, view=None):
        try:
            await interaction.edit_original_response(content=content, view=view)
        except Exception:
            try:
                await interaction.followup.send(content or '\u200b', view=view, ephemeral=True)
            except Exception:
                pass

    class SelectBackupView(discord.ui.View):
        def __init__(self):
            super().__init__(timeout=60)
            options = []
            for fn, _ in choices:
                label = fn.replace(f"{safe_name}__", "")[:-5]
                options.append(discord.SelectOption(label=label, value=fn, description=fn[-20:]))
            self.selector = discord.ui.Select(placeholder='復元するバックアップを選んでください', options=options, min_values=1, max_values=1)
            self.selector.callback = self.on_select
            self.add_item(self.selector)

        async def on_select(self, interaction_btn: discord.Interaction):
            await self.restore_selected(interaction_btn, self.selector.values[0])

        async def restore_selected(self, interaction_btn: discord.Interaction, filename: str):
            # ビューを無効化
            for item in self.children:
                item.disabled = True
            await _edit(content=f'📤 復元を開始します… {filename}', view=self)

            full = os.path.join(CHAT_DIR, filename)
            try:
                with open(full, 'r', encoding='utf-8') as f:
                    payload = json.load(f)
            except Exception as e:
                return await _edit(content=f'読み込みに失敗しました: {e}', view=None)

            msgs = payload.get('messages', [])
            # 投稿は順序通り（古い→新しい）
            sent = 0
            for m in msgs:
                content = m.get('content')
                # Fallback: if content is empty, try to summarize embeds
                if not content:
                    embeds = m.get('embeds') or []
                    if embeds:
                        titles = [e.get('title') for e in embeds if isinstance(e, dict)]
                        descs = [e.get('description') for e in embeds if isinstance(e, dict)]
                        summary = ' / '.join([t for t in titles if t]) or ''
                        if descs and not summary:
                            summary = (descs[0] or '')[:200]
                        if summary:
                            content = f"[EMBED] {summary}"
                atts = m.get('attachments') or []
                if atts:
                    att_lines = "\n".join([f"[添付] {a.get('filename')} → {a.get('url')}" for a in atts])
                    content = ((content or '') + "\n\n" + att_lines).strip()
                if not content or content.strip() == '':
                    content = '(空メッセージ)'
                try:
                    await channel.send(content)
                    sent += 1
                    if sent % 20 == 0:
                        await _edit(content=f'⏳ 復元中… {sent}/{len(msgs)}', view=self)
                    # 軽いウェイトでRate Limitを回避
                    await asyncio.sleep(0.35)
                except Exception:
                    # 送信失敗はスキップ
                    pass

            await _edit(content=f'✅ 復元完了: {sent}/{len(msgs)} 件を投稿しました。', view=None)

    view = SelectBackupView()
    await _edit(content='候補が見つかりました。復元するバックアップを選んでください。', view=view)


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

    await _progress(f'✅ テキストチャンネル {len(stored_text) if os.path.exists(TEXT_FILE) else 0} 件を復元。次：ボイスチャンネル…')

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
    voice_targets = list(guild.voice_channels)
    category_targets = list(guild.categories)
    role_targets = [r for r in guild.roles if (not r.is_default()) and (not r.managed)]  # @everyone と連携ロール除外(権限なしになるので)

    warning = (
        '⚠️ **超危険**: 次のリソースを削除します\n'
        f'- テキストチャンネル: {len(text_targets)}\n'
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
            await progress(f'✅ テキストチャンネル {deleted_text}/{len(text_targets)} 削除完了。次：ボイスチャンネル…')

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
        if intents.message_content and not enable_msg_content:
            # no-op safeguard
            pass
        if os.getenv('ENABLE_MESSAGE_CONTENT_INTENT', '0').lower() in ('1','true','yes'):
            print('WARNING: ENABLE_MESSAGE_CONTENT_INTENT is set. Ensure "Message Content Intent" is enabled in the Developer Portal if your bot is in 100+ servers.')
        try:
            bot.run(TOKEN)
        except discord.errors.PrivilegedIntentsRequired as e:
            print('起動に失敗しました: Privileged intents が有効になっていません。')
            print('Developer Portal のアプリ設定で "Server Members Intent" と/または "Message Content Intent" を有効化するか、')
            print('もしくは .env で ENABLE_MEMBERS_INTENT を無効にしてください。')
            raise
