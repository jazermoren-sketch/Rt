import discord
from discord.ext import commands
import os
import json
import datetime
import aiohttp

# --- 1. الإعدادات الأساسية ---
intents = discord.Intents.default()
intents.message_content = True 
bot = commands.Bot(command_prefix='!', intents=intents)

# ملفات البيانات
CHANNELS_FILE = "channels.txt"
LOG_CHANNEL_FILE = "log_channel.txt"
WARNINGS_DB = "warnings_db.json"
CONFIG_FILE = "mod_config.json"

# القاموس (الفرانكو)
mapping = {
    'ح': '7', 'ع': '3', 'خ': '5', 'ط': '6', 'ص': '9', 'ض': 'd', 
    'ق': '8', 'ء': '2', 'ؤ': '2', 'ئ': '2', 'أ': '1', 'إ': '1', 'آ': '1'
}

webhooks_cache = {}

# --- 2. دوال إدارة الملفات وقاعدة البيانات ---
def load_list(file):
    if os.path.exists(file):
        with open(file, "r") as f: return [int(line.strip()) for line in f if line.strip().isdigit()]
    return []

def save_list(file, data):
    with open(file, "w") as f:
        for item in data: f.write(f"{item}\n")

def load_db():
    if os.path.exists(WARNINGS_DB):
        with open(WARNINGS_DB, "r") as f: return json.load(f)
    return {}

def save_db(data):
    with open(WARNINGS_DB, "w") as f: json.dump(data, f, indent=4)

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r") as f: return json.load(f)
    return {"max_warns": 3, "action": "kick"}

def save_config(config):
    with open(CONFIG_FILE, "w") as f: json.dump(config, f, indent=4)

allowed_channels = load_list(CHANNELS_FILE)
warn_log_channel_id = load_list(LOG_CHANNEL_FILE)[0] if load_list(LOG_CHANNEL_FILE) else None
mod_config = load_config()

# --- 3. نظام العقوبات (Punishment System) ---

class PunishmentView(discord.ui.View):
    def __init__(self, user):
        super().__init__(timeout=None)
        self.user = user

    @discord.ui.button(label="Time Out", style=discord.ButtonStyle.secondary)
    async def timeout(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.user.timeout(datetime.timedelta(minutes=60), reason="Auto-Punishment")
        await interaction.response.send_message(f"✅ تم عمل Timeout لـ {self.user.mention}", ephemeral=True)

    @discord.ui.button(label="Kick", style=discord.ButtonStyle.danger)
    async def kick(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.user.kick(reason="Auto-Punishment")
        await interaction.response.send_message(f"✅ تم طرد {self.user.mention}", ephemeral=True)

    @discord.ui.button(label="Ban", style=discord.ButtonStyle.danger)
    async def ban(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.user.ban(reason="Auto-Punishment")
        await interaction.response.send_message(f"✅ تم حظر {self.user.mention}", ephemeral=True)

# --- 4. نظام التحذيرات (Mod System) ---

class WarnReasonModal(discord.ui.Modal, title='إرسال تحذير للمنشور'):
    reason = discord.ui.TextInput(label='سبب التحذير', style=discord.TextStyle.paragraph, placeholder='اكتب السبب هنا...', required=True)

    def __init__(self, target_user, original_msg, target_channel):
        super().__init__()
        self.target_user = target_user
        self.original_msg = original_msg
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        global warn_log_channel_id
        await interaction.response.defer(ephemeral=True)

        if not warn_log_channel_id:
            await interaction.followup.send("❌ لم يتم تحديد قناة للتحذيرات!")
            return

        log_channel = interaction.guild.get_channel(warn_log_channel_id)
        if not log_channel:
            await interaction.followup.send("❌ قناة التحذيرات غير موجودة.")
            return

        db = load_db()
        u_id = str(self.target_user.id)
        if u_id not in db:
            db[u_id] = {"count": 0, "reasons": []}
        
        db[u_id]["count"] += 1
        db[u_id]["reasons"].append(self.reason.value)
        save_db(db)

        embed = discord.Embed(title="⚠️ معلومات التحذير", color=discord.Color.red())
        embed.add_field(name="المُحذِر:", value=interaction.user.mention, inline=True)
        embed.add_field(name="المُحذَّر:", value=self.target_user.mention, inline=True)
        embed.add_field(name="السبب:", value=self.reason.value, inline=False)
        embed.add_field(name="القناة:", value=self.target_channel.mention, inline=True)
        content_text = self.original_msg.content[:100] if self.original_msg.content else "بدون نص"
        embed.add_field(name="نص المنشور:", value=content_text, inline=False)
        embed.set_footer(text=f"الوقت: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        
        if self.original_msg.attachments:
            embed.set_image(url=self.original_msg.attachments[0].url)

        await log_channel.send(embed=embed)
        await interaction.followup.send(f"✅ تم تسجيل التحذير في <#{warn_log_channel_id}>")

        if db[u_id]["count"] >= mod_config["max_warns"]:
            view = PunishmentView(self.target_user)
            await interaction.followup.send(f"🚨 **تنبيه!** {self.target_user.mention} وصل للحد الأقصى! اختر عقوبة:", view=view, ephemeral=False)

class SellerDetailsView(discord.ui.View):
    def __init__(self, seller_name, seller_id, channel_id, original_msg):
        super().__init__(timeout=None)
        self.seller_name = seller_name
        self.seller_id = seller_id
        self.channel_id = channel_id
        self.original_msg = original_msg

    @discord.ui.button(label="View Profile", style=discord.ButtonStyle.secondary)
    async def view_profile(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🔗 [اضغط هنا لزيارة الملف الشخصي](https://discord.com/users/{self.seller_id})", ephemeral=True)

    @discord.ui.button(label="تحذير البائع", style=discord.ButtonStyle.danger)
    async def warn_seller(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not interaction.user.guild_permissions.administrator:
            await interaction.response.send_message("❌ هذا الزر للمشرفين فقط!", ephemeral=True)
            return
        await interaction.response.send_modal(WarnReasonModal(interaction.user, self.original_msg, interaction.guild.get_channel(self.channel_id)))

class MainSalesView(discord.ui.View):
    def __init__(self, seller_name, seller_id, channel_id, original_msg):
        super().__init__(timeout=None)
        self.seller_name = seller_name
        self.seller_id = seller_id
        self.channel_id = channel_id
        self.original_msg = original_msg

    @discord.ui.button(label="تواصل مع البائع", style=discord.ButtonStyle.primary)
    async def contact_seller(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = discord.Embed(title="تفاصيل البائع", color=discord.Color.blue())
        embed.add_field(name="البائع:", value=self.seller_name, inline=True)
        embed.add_field(name="الايدي:", value=f"`{self.seller_id}`", inline=True)
        embed.add_field(name="القناة:", value=f"<#{self.channel_id}>", inline=True)
        await interaction.response.send_message(embed=embed, view=SellerDetailsView(self.seller_name, self.seller_id, self.channel_id, self.original_msg), ephemeral=True)

# --- 5. نظام التشهير (Scam Exposure System) ---

class ScamReportModal(discord.ui.Modal, title='تقديم بلاغ تشهير بنصاب'):
    scammer_name = discord.ui.TextInput(label='اسم النصاب', placeholder='مثال: @ScammerName', required=True)
    scammer_id = discord.ui.TextInput(label='آيدي النصاب', placeholder='1234567890...', required=True)
    amount = discord.ui.TextInput(label='المبلغ المفقود', placeholder='مثال: 50$', required=True)
    subject = discord.ui.TextInput(label='الموضوع', placeholder='مثال: نصب في حساب', required=True)
    details = discord.ui.TextInput(label='التفاصيل', style=discord.TextStyle.paragraph, placeholder='اشرح ماذا حدث...', required=True)
    evidence_url = discord.ui.TextInput(label='رابط الدليل (صورة)', placeholder='ضع رابط الصورة هنا', required=False)

    def __init__(self, reporter, target_channel):
        super().__init__()
        self.reporter = reporter
        self.target_channel = target_channel

    async def on_submit(self, interaction: discord.Interaction):
        embed = discord.Embed(title="🚫 تشهير بنصاب 🚫", description="**تم التحقق من هذا التشهير من قبل الإدارة**", color=discord.Color.red())
        embed.add_field(name="👤 المبلغ", value=f"`{self.amount.value}`", inline=True)
        embed.add_field(name="🆔 الآيدي", value=f"`{self.scammer_id.value}`", inline=True)
        embed.add_field(name="📝 الموضوع", value=f"`{self.subject.value}`", inline=False)
        embed.add_field(name="👤 النصاب", value=f"{self.scammer_name.value}", inline=True)
        embed.add_field(name="📢 المبلّغ", value=f"{self.reporter.mention}", inline=True)
        embed.add_field(name="📄 التفاصيل", value=self.details.value, inline=False)

        if self.evidence_url.value:
            embed.set_image(url=self.evidence_url.value)
        
        embed.set_footer(text=f"تم النشر في: {self.target_channel.name} | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        await self.target_channel.send(content="@everyone ⚠️ احذروا هذا النصاب!", embed=embed)
        await interaction.response.send_message("✅ تم إرسال بلاغك بنجاح.", ephemeral=True)

class ScamReportView(discord.ui.View):
    def __init__(self, target_channel):
        # جعلنا timeout=None لكي يبقى الزر يعمل دائماً حتى بعد إعادة تشغيل البوت
        super().__init__(timeout=None)
        self.target_channel = target_channel

    # أضفنا row=0 لضمان أن هذا الزر يأخذ الصف الأول دائماً
    @discord.ui.button(
        label="تقديم بلاغ تشهير 🚨", 
        style=discord.ButtonStyle.danger, 
        custom_id="scam_report_btn",
        row=0  # هذا هو الحل! يحدد مكان الزر في الصف الأول
    )
    async def report_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ScamReportModal(interaction.user, self.target_channel))
        
# --- 6. الأوامر الإدارية ---

@bot.command()
@commands.has_permissions(administrator=True)
async def set_log_channel(ctx, channel: discord.TextChannel):
    global warn_log_channel_id
    warn_log_channel_id = channel.id
    save_list(LOG_CHANNEL_FILE, [warn_log_channel_id])
    await ctx.send(f"✅ تم تحديد قناة التحذيرات: {channel.mention}")

@bot.command()
@commands.has_permissions(administrator=True)
async def add_channel(ctx, channel: discord.TextChannel):
    if channel.id not in allowed_channels:
        allowed_channels.append(channel.id)
        save_list(CHANNELS_FILE, allowed_channels)
        await ctx.send(f"✅ تمت إضافة {channel.mention} لنظام المبيعات.")
    else:
        await ctx.send("⚠️ القناة مضافة مسبقاً.")

@bot.command()
@commands.has_permissions(administrator=True)
async def remove_channel(ctx, channel: discord.TextChannel):
    if channel.id in allowed_channels:
        allowed_channels.remove(channel.id)
        save_list(CHANNELS_FILE, allowed_channels)
        await ctx.send(f"❌ تم حذف {channel.mention}")
    else:
        await ctx.send("⚠️ القناة ليست في القائمة.")

@bot.command()
@commands.has_permissions(administrator=True)
async def warn_stats(ctx):
    db = load_db()
    if not db: return await ctx.send("❌ لا يوجد أي تحذيرات مسجلة.")
    embed = discord.Embed(title="📊 إحصائيات التحذيرات", color=discord.Color.gold())
    for u_id, info in db.items():
        embed.add_field(name=f"ID: {u_id}", value=f"تحذيرات: {info['count']}", inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def user_warns(ctx, user: discord.User):
    db = load_db()
    u_id = str(user.id)
    if u_id not in db: return await ctx.send(f"✅ {user.display_name} ليس لديه تحذيرات.")
    info = db[u_id]
    embed = discord.Embed(title=f"📜 سجل: {user.display_name}", color=discord.Color.orange())
    embed.add_field(name="العدد:", value=info['count'], inline=True)
    embed.add_field(name="الأسباب:", value="\n".join(info['reasons']), inline=False)
    await ctx.send(embed=embed)

@bot.command()
@commands.has_permissions(administrator=True)
async def set_auto_mod(ctx, max_warns: int, action: str):
    global mod_config
    config = load_config()
    config["max_warns"] = max_warns
    config["action"] = action.lower()
    save_config(config)
    await ctx.send(f"✅ تم ضبط النظام: العقوبة هي `{action}` عند `{max_warns}` تحذيرات.")

@bot.command()
@commands.has_permissions(administrator=True)
async def setup_report(ctx, channel: discord.TextChannel):
    view = ScamReportView(channel)
    embed = discord.Embed(
        title="📢 نظام التشهير بالصيادين والنصابين",
        description="إذا تعرضت لعملية نصب، اضغط على الزر أدناه لتقديم بلاغ رسمي وسنقوم بنشره للجميع.",
        color=discord.Color.blue()
    )
    await ctx.send(embed=embed, view=view)
    await ctx.send(f"✅ تم إعداد نظام البلاغات في {channel.mention}", delete_after=5)

# --- 7. المحرك الأساسي ---

@bot.event
async def on_ready():
    print(f'✅ Ultimate Bot Online: {bot.user.name}')

@bot.event
async def on_message(message):
    if message.author == bot.user or message.webhook_id is not None: return

    if message.channel.id in allowed_channels:
        text = message.content
        for ar, fr in mapping.items(): text = text.replace(ar, fr)

        try:
            if message.channel.id not in webhooks_cache:
                webhook = await message.channel.create_webhook(name=f"Sales_{message.channel.name}")
                webhooks_cache[message.channel.id] = webhook
            
            current_webhook = webhooks_cache[message.channel.id]
            view = MainSalesView(message.author.display_name, message.author.id, message.channel.id, message)
            files = [await a.to_file() for a in message.attachments] if message.attachments else []

            await current_webhook.send(
                content=text if text else None,
                username=message.author.display_name,
                avatar_url=message.author.display_avatar.url,
                view=view,
                files=files
            )
            await message.delete()
        except Exception as e:
            print(f"Error: {e}")
            await message.channel.send(text)

    await bot.process_commands(message)

bot.run('YOUR_BOT_TOKEN')