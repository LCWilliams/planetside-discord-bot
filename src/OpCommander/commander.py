# OPS COMMANDER
# Provides a simple interface that allows those with permissions to:
# Alert -> Starts an alert coroutine, users signed up are pinged at 10 minute intervals.  Channels are created in prep.
# Start Ops -> Self explanitory, starts an op event.
# Debrief -> Begin a debrief process; after 5 minutes normal users are moved to 'planetside' channel, commanders are moved to 'command' channel, channels are cleaned up.
#			 Users are offered the ability to provide anonymised feedback via the bot regarding the event.  This is fed to the command channel.
# End Ops -> Removes the signup.


# EMBEDS:
# 1. OpInfo Embed: show if any options applied, signed up users
# 2. Connection Embed: Show status of signed up users (discord online|discord comms|Online Ingame)
# 3. SessionStats Embed: Start time, end time, user stats, link to Honu.
# 4. SessionFeedback: Place to store player feedback.

import discord
import discord.ext
from discord.ext import tasks, commands
import auraxium
from  OpCommander.events import OpsEventTracker

import enum
import sched
import datetime, dateutil.relativedelta

import botUtils
from botUtils import BotPrinter as BUPrint
from botUtils import ChannelPermOverwrites as ChanPermOverWrite
from botData.settings import BotSettings as botSettings
from botData.settings import Commander as commanderSettings
from botData.settings import Messages as botMessages

from opsManager import OperationManager as OpManager
import botData.operations
from botData.operations import OperationData as OpsData
from OpCommander.status import CommanderStatus


class Commander():
	"""
	# COMMANDER
	Class containing functions and members used during a live, running Operation
	"""
	vBotRef: commands.Bot
	def __init__(self, p_opData: OpsData) -> None:
		BUPrint.Info("Ops Commander created")
		self.vOpData : OpsData = p_opData # The OpData
		self.vCommanderStatus = CommanderStatus.Init

		# Auraxium client & Op event tracker
		self.vAuraxClient = auraxium.EventClient()
		self.vOpsEventTracker = OpsEventTracker(p_aurClient=self.vAuraxClient)

		# Alert & Autostart Scheduler
		self.vAutoAlerts = sched.scheduler()

		#DiscordElements:
		self.vGuild: discord.Guild = None
		self.commanderMsg: discord.Message = None # Message object used to edit the commander. Set during first post.
		self.commanderChannel: discord.TextChannel = None # Channel for the Commander to be posted in.
		self.notifChn: discord.TextChannel = None # Channel used to display notifications
		self.vCategory: discord.CategoryChannel = None # Category object to keep the Ops self contained. All channels are created within here, except non-soberdogs feedback
		self.standbyChn: discord.VoiceChannel = None # Standby channel voice connected users are moved into during start.
		self.lastStartAlert: discord.Message = None # Last Start alert sent, used to store + remove a previous alert to not flood the channel.
		self.participants = [] # List of participating Members
		self.participantsUserData = [] # Not yet used- will contain UserData for stat tracking.

	async def GenerateCommander(self):
		"""
		# GENERATE COMMANDER

		Either creates, or updates an existing Commander, using the current status.
		The commander does not include the INFO embed, since it does not need to be updated.

		If the Ops has not started, no embeds are added.  
		A message is shown displaying the next auto-alert time, or auto-start time.
		"""
		vMessageView = self.GenerateView_Commander()
		vEmbeds:list = []
		
		# Pre-Started display
		if self.vCommanderStatus.value < CommanderStatus.Started.value:
			pass
		else: # Started display:
			vEmbeds.append( self.GenerateEmbed_Connections())
			if commanderSettings.bEnableLiveTracking:
				vEmbeds.append( self.GenerateEmbed_Session() )

		await self.commanderMsg.edit(content=f"**OP COMMANDER** *Last update: {datetime.datetime.now()}*", view=vMessageView, embeds=vEmbeds)


	async def CommanderSetup(self):
		"""
		# COMMANDER SETUP
		Sets up the commander for the operation (category & channels), should only be called once.
		"""
		if(self.vCommanderStatus == CommanderStatus.Init):
			BUPrint.Info("Operation Commander first run setup...")
			# Perform first run actions.
			
			# Get & set guild ref.
			self.vGuild = await self.vBotRef.fetch_guild(botSettings.discordGuild)

			# Create category and channels.
			await self.CreateCategory()
			await self.CreateTextChannels()
			await self.CreateVoiceChannels()



			# Add Commander text channel and post Op Info embed (the one that isn't repeatedly updated)
			BUPrint.Debug("	-> Posting Ops Info")

			
			opString = f"*OPERATION INFORMATION for {self.vOpData.name}*"
			managingUser = self.vGuild.get_member(self.vOpData.managedBy)			
			if managingUser != None:
				opString = f"{managingUser.mention} {opString}"
			
			await self.commanderChannel.send(
				opString, 
				embed=self.GenerateEmbed_OpInfo()
			)

			#Post standby commander, to set commander messageID; all future calls should use GenerateCommander instead.
			BUPrint.Debug("	-> Posting Commander")
			vCommanderMsg = f"**COMMANDER ON STANDBY**\n"
			if commanderSettings.bAutoStartEnabled:
				vCommanderMsg += "Auto-Start is enabled.  \n> *This Commander will automatically start the operation.*\n> *To start the operation early, press* ***START***."
			self.commanderMsg =  await self.commanderChannel.send(vCommanderMsg, view=self.GenerateView_Commander())
			
			
			# Setup Alerts
			# Always post first alert on commander creation:
			self.lastStartAlert = await self.notifChn.send( await self.GenerateAlertMessage() )
			
			if commanderSettings.bAutoAlertsEnabled:
				pass

			# Setup AutoStart
			if self.vOpData.options.bAutoStart and commanderSettings.bAutoStartEnabled:
				pass


			# Set to standby and return.
			self.vCommanderStatus = CommanderStatus.Standby
			return
		else:
			BUPrint.Info("Commander has already been set up!")



	async def CreateCategory(self):
		"""
		# CREATE CATEGORY
		Creates a category to self-contain the Op.
		If an existing category with the same name exists, that is used instead (and permission overwrites applied.)

		## RETURN: `bool` True if successful.
		"""
		for category in self.vBotRef.guilds[0].categories:
			if category.name.lower() == self.vOpData.name.lower():
				self.vCategory = category
				BUPrint.Debug("Existing category with matching name found.  Using it instead.")
				return True

		# No existing category, create one.
		if self.vCategory == None:
			BUPrint.Debug("No existing category with matching name, creating as normal")

			if self.vCategory == None:
				BUPrint.Debug("	-> Create category.")
				try:
					self.vCategory = await self.vGuild.create_category(
						name=f"{self.vOpData.name}",
						reason=f"Creating category for {self.vOpData.fileName}",
						overwrites=ChanPermOverWrite.level3
					)
				except discord.Forbidden as error:
					BUPrint.LogErrorExc("	-> Unable to create category; invalid permissions!", error)
					return False
				except discord.HTTPException as error:
					BUPrint.LogErrorExc("	-> Invalid form", error)
					return False
				except TypeError as error:
					BUPrint.LogErrorExc("	-> Invalid permission overwrites", error)
					return False


	async def CreateTextChannels(self):
		"""
		# CREATE TEXT CHANNELS
		Creates text channels used for the Operation.
		If existing channels are found, they are used instead.
		"""
		# Find existing Commander & Notif channels
		for txtChannel in self.vCategory.text_channels:
			if txtChannel.name.lower() == botData.operations.DefaultChannels.opCommander.lower():
				BUPrint.Debug("Existing op commander channel found in category, using that instead.")
				self.commanderChannel = txtChannel
				await self.commanderChannel.purge()

			if txtChannel.name.lower() == botData.operations.DefaultChannels.notifChannel.lower():
				BUPrint.Debug("Existing notification channel found in category, using that instead.")
				self.notifChn = txtChannel
				await self.notifChn.purge()

		# Manually create Commander & Notif channel if not already present
		if self.commanderChannel == None:
			self.commanderChannel = await self.vCategory.create_text_channel(
				name=botData.operations.DefaultChannels.opCommander,
				overwrites=ChanPermOverWrite.level2
			)

		if self.notifChn == None:
			self.notifChn = await self.vCategory.create_text_channel(
				name=botData.operations.DefaultChannels.notifChannel,
				overwrites=ChanPermOverWrite.level3_readOnly
			)

		# Add non-existing channels for custom text channels
		txtChannelName:str
		for txtChannelName in botData.operations.DefaultChannels.textChannels:
			if txtChannelName.lower() not in self.vCategory.text_channels:
				await self.vCategory.create_text_channel(
					name=txtChannelName,
					overwrites=ChanPermOverWrite.level3
				)


	async def CreateVoiceChannels(self):
		"""
		# CRETE VOICE CHANNELS
		Creates voice channels used for the Ops.
		Voice channels include persistent and custom entries.
		"""
		# Create always present voice channels:
		bAlreadyExists = False
		for existingChannel in self.vCategory.voice_channels:
			if existingChannel.name.lower() == botData.operations.DefaultChannels.standByChannel.lower():
				bAlreadyExists = True
				BUPrint.Debug("Existing standby channel found.")
				self.standbyChn = existingChannel
				break

		if self.standbyChn == None:
			self.standbyChn = await self.vCategory.create_voice_channel(name=botData.operations.DefaultChannels.standByChannel)

		BUPrint.Debug("	-> Creating default chanels")
		if len(botData.operations.DefaultChannels.persistentVoice) != 0:
			for newChannel in botData.operations.DefaultChannels.persistentVoice:

				bAlreadyExists = False
				for existingChannel in self.vCategory.voice_channels:
					if existingChannel.name == newChannel:
						bAlreadyExists = True
						BUPrint.Debug(f"Existing channel for: {newChannel} found.")
						break

				if not bAlreadyExists:
					BUPrint.Debug(f"No existing channel for {newChannel} found.  Creating new voice channel!")
					channel:discord.VoiceChannel = await self.vCategory.create_voice_channel(name=newChannel)


		# Create custom voice channels if present
		if len(self.vOpData.voiceChannels) != 0 and self.vOpData.voiceChannels[0] != "":
			BUPrint.Debug("	-> Voice channels specified...")
			newChannel:str
			for newChannel in self.vOpData.voiceChannels:
				BUPrint.Debug(f"	-> Adding channel: {newChannel}")

				bAlreadyExists = False
				for existingChannel in self.vCategory.voice_channels:
					if existingChannel.name.lower() == newChannel.lower():
						bAlreadyExists = True
						BUPrint.Debug(f"Existing channel for: {newChannel} found.")
						break
				if not bAlreadyExists:
					BUPrint.Debug(f"No existing channel for {newChannel} found.  Creating new voice channel!")
					channel = await self.vCategory.create_voice_channel(name=newChannel)
		
		
		else: # No custom voice channels given, use default
		
			BUPrint.Debug("	-> No voice channels specified, using defaults...")
			for newChannel in botData.operations.DefaultChannels.voiceChannels:
				BUPrint.Debug(f"	-> Adding channel: {newChannel}")
	
				bAlreadyExists = False
				for existingChannel in self.vCategory.voice_channels:
					if existingChannel.name == newChannel:
						bAlreadyExists = True
						BUPrint.Debug(f"Existing channel for: {newChannel} found.")
						break

				if not bAlreadyExists:
					BUPrint.Debug(f"No existing channel for {newChannel} found.  Creating new voice channel!")
					channel = await self.vCategory.create_voice_channel(name=newChannel)
	
	
	async def RemoveChannels(self):
		"""
		# REMOVE CHANNELS
		Removes the channels and category related to the Ops.
		"""
		BUPrint.Debug("Removing Channels")

		# Remove Text channels
		for textChannel in self.vCategory.text_channels:
			BUPrint.Debug(f"	-> Removing {textChannel.name}")
			await textChannel.delete(reason="Op Commander removing channel.")

		# Get all connected users.
		userList = []
		voiceChannel: discord.VoiceChannel
		for voiceChannel in self.vCategory.voice_channels:
			userList += voiceChannel.members

		# Get fallback channel		
		user:discord.Member
		fallbackChannel = self.vBotRef.get_channel(botSettings.fallbackVoiceChat)

		# Move connected users to fallback channel
		for user in userList:
			BUPrint.Debug(f"Attempting to move {user.display_name} to fallback channel.")
			await user.move_to(channel=fallbackChannel, reason="Moving user from Ops channel to fallback.")

		# Remove channels
		for voiceChannel in self.vCategory.voice_channels:
			await voiceChannel.delete(reason="Auto removal of channels after Operation end.")

		# Remove empty category
		await self.vCategory.delete(reason="Auto removal of category after Operation end.")

		#removethisinamoment
		await self.vAuraxClient.close()


	async def PreStart(self):
		"""
		# PRE START

		"""


	async def GenerateAlertMessage(self):
		"""
		# GENERATE ALERT MESSAGE
		Convenience function to generate a pre-formatted message string for pre-start alerts.
		"""
		vParticipantStr = await self.GetParticipants()

		vMessage = f"**REMINDER: {self.vOpData.name} STARTS {botUtils.DateFormatter.GetDiscordTime( self.vOpData.date, botUtils.DateFormat.Dynamic )}**\n"
		vMessage += vParticipantStr
		if commanderSettings.bAutoMoveVCEnabled:
			vMessage += f"\n\n*{botMessages.OpsAutoMoveWarn}*"

		return vMessage


	async def GetParticipants(self):
		"""
		# GET PARTICIPANTS
		Sets the self.participants + participantUserData.
		## RETURN: `str` of `member.mention` for each user.

		### TODO: Get UserData objects for user library.
		"""
		vParticipantStr = ""
		role: botData.operations.OpRoleData
		member:discord.Member = None
		BUPrint.Debug("Getting roled participants...")
		for role in self.vOpData.roles:
			for user in role.players:
				member = self.vGuild.get_member(user)
				if member == None:
					member = await self.vGuild.fetch_member(user)
				vParticipantStr += f" {member.mention} "
				self.participants.append(member)

		BUPrint.Debug("Getting reserved participants...")
		if self.vOpData.options.bUseReserve:
			for user in self.vOpData.reserves:
				member = self.vGuild.get_member(user)
				if member == None:
					member = await self.vGuild.fetch_member(user)
				vParticipantStr += f" {member.mention} "
				self.participants.append(member)
		

	
		return vParticipantStr


	def GenerateEmbed_OpInfo(self):
		"""
		# GENERATE EMBED : OpInfo

		Creates an Embed for Operation Info.
		"""
		vEmbed = discord.Embed(colour=botUtils.Colours.commander.value, title=f"**OPERATION INFO** | {self.vOpData.name}")

		# START | SIGNED UP
		vEmbed.add_field(
			name=f"Start {botUtils.DateFormatter.GetDiscordTime(self.vOpData.date, botUtils.DateFormat.Dynamic)}", 
			value=f"{botUtils.DateFormatter.GetDiscordTime(self.vOpData.date, botUtils.DateFormat.DateTimeLong)}", 
			inline=True
		)

		# DISPLAY OPTIONS & DATA
		vEmbed.add_field(
			name="Auto Start", 
			value=f"{commanderSettings.bAutoStartEnabled}"
		)
		
		alertInterval = commanderSettings.autoPrestart / commanderSettings.autoAlertCount
		vEmbed.add_field(
			name="Alerts", 
			value=f"Enabled: *{commanderSettings.bAutoAlertsEnabled}*\nSending: *{commanderSettings.autoAlertCount}(+1)*\nInterval: {alertInterval} mins"
		)
		
		vSignedUpCount = 0
		vLimitedRoleCount = 0
		vFilledLimitedRole = 0
		role: botData.operations.OpRoleData
		for role in self.vOpData.roles:
			vSignedUpCount += len(role.players)
			if role.maxPositions > 0:
				vLimitedRoleCount += role.maxPositions
				vFilledLimitedRole += len(role.players)

		vEmbed.add_field(
			name="ROLE OVERVIEW",
			value=f"Total Players: *{vSignedUpCount}*\nRoles: *{len(self.vOpData.roles)}*\nRole Spaces: *{vFilledLimitedRole}/{vLimitedRoleCount}*",
			inline=True
			)
		
		usersInReserve = "*Disabled*"
		if self.vOpData.options.bUseReserve:
			if len(self.vOpData.reserves) != 0:
				usersInReserve = ""
				for user in self.vOpData.reserves:
					usersInReserve += f"{self.vBotRef.get_user(int(user)).mention}\n"
			else: usersInReserve = "*None*"

		vEmbed.add_field(
			name=f"RESERVES: {len(self.vOpData.reserves)}",
			value=usersInReserve,
			inline=True
			)


		bFirstRole = False
		role: botData.operations.OpRoleData
		for role in self.vOpData.roles:
			
			vUsersInRole = "*None*"
			if len(role.players) != 0:
				vUsersInRole = ""
				for user in role.players:
					vUsersInRole += f"{self.vBotRef.get_user(int(user)).mention}\n"
				
				vEmbed.add_field( name=f"{self.GetRoleName(role)}", value=vUsersInRole, inline=bFirstRole)
				bFirstRole = True


		return vEmbed


	def GenerateEmbed_Connections(self):
		"""
		# GENERATE EMBED : OpInfo

		Creates an Embed for player connections.
		"""
		vEmbed = discord.Embed(colour=discord.Colour.from_rgb(200, 200, 255), title="CONNECTIONS", description="Discord and PS2 connection information for participants.")

		vEmbed.add_field(name="Empty field", value="empty field")

		return vEmbed

	def GenerateEmbed_Session(self):
		"""
		# GENERATE EMBED : Session

		Creates an Embed for displaying session stats.
		"""
		vEmbed = discord.Embed(colour=discord.Colour.from_rgb(200, 200, 255), title="SESSION", description="Displays session stats.")

		vEmbed.add_field(name="Empty field", value="empty field")

		return vEmbed


	def GenerateEmbed_Feedback(self):
		"""
		# GENERATE EMBED : Feedback

		Creates an Embed for displaying player provided feedback, offering anonymity.
		"""
		pass


	def GenerateView_UserFeedback(self):
		"""
		GENERATE VIEW: User Feedback:

		Creates a view providing a button to users to send feedback.
		"""
		pass


	def GenerateView_Commander(self):
		"""
		# GENERATE VIEW: COMMANDER

		Creates a commander view.  Buttons status are updated depending on Op Status

		## RETURNS: `discord.ui.View`

		"""
		newView = discord.ui.View(timeout=None)
		# Button Objects
		btnStart = Commander_btnStart(p_commanderParent=self)
		btnEnd = Commander_btnEnd(p_commanderParent=self)
		btnDebrief = Commander_btnDebrief(p_commanderParent=self)

		# Configure button disabled.
		# Before op Started:
		if self.vCommanderStatus.value < CommanderStatus.Started.value:
			btnEnd.disabled = True
			btnDebrief.disabled = True

		
		# Ops Started:
		if self.vCommanderStatus.value == CommanderStatus.Started.value:
			btnStart.disabled = True
			btnDebrief.disabled = False
			btnEnd.disabled = False

		newView.add_item(btnStart)
		newView.add_item(btnDebrief)
		newView.add_item(btnEnd)

		return newView


	async def StartOperation(self):
		"""
		# START OPERATION
		Modifies and updates op signup post.
		Modifies commander status, then updates commander.
		Starts tracking, if enabled.
		"""
		self.vOpData.status = OpsData.status.started
		vOpMan = OpManager()
		await vOpMan.UpdateMessage(self.vOpData)
		self.vCommanderStatus = CommanderStatus.Started
		await self.GetParticipants()
		await self.GenerateCommander()

		if commanderSettings.bAutoStartEnabled:
			# TODO: start tracking here.
			pass

		if commanderSettings.bAutoMoveVCEnabled:
			BUPrint.Debug("Moving VC connected participants")
			await self.MoveUsers(p_moveToStandby=True)


	async def EndOperation(self):
		"""
		# END OPERATION
		Removes the live Op from the Operations manager, 
		then cleans up the Op Commander.
		"""
		self.vCommanderStatus = CommanderStatus.Ended

		await self.vAuraxClient.close()

		# Removes the operation posting.
		vOpMan = OpManager()
		await vOpMan.RemoveOperation(self.vOpData)

		# Move users before removing channels.
		await self.MoveUsers(p_moveToStandby=False)
		
		# Yeetus deleetus the category; as if it never happened!
		await self.RemoveChannels()


	def GetRoleName(self, p_role:botData.operations.OpRoleData):
		"""
		# GET ROLE NAME
		Convenience function to get a role name with icon prefix if applicable, and append current/max, if applicable.	
		"""
		vRoleName = ""
		if p_role.roleIcon != "-":
			vRoleName = f"{p_role.roleIcon}{p_role.roleName}"
		else:
			vRoleName = p_role.roleName

		if p_role.maxPositions > 0:
			vRoleName += f" ({len(p_role.players)}/{p_role.maxPositions})"
		else:
			vRoleName += f" ({len(p_role.players)})"

		return vRoleName

	async def MoveUsers(self, p_moveToStandby:bool = True):
		"""
		# MOVE USERS
		Moves currently connected users to the standby channel.
		`p_moveToStandby` : If false, users are instead moved to the fallback channel.
		"""
		participant: discord.Member
		fallbackChannel = self.vGuild.get_channel(botSettings.fallbackVoiceChat)
		# connectedUserIDs = {}
		vConnectedUsers = []

		if p_moveToStandby and commanderSettings.bAutoMoveVCEnabled: # Moving signed up users to standby
			for voiceChannel in self.vGuild.voice_channels:
				for user in voiceChannel.members:
					if user in self.participants:
						vConnectedUsers.append(user)

				# connectedUserIDs = {**connectedUserIDs, **voiceChannel.voice_states}
		else:
			for voiceChannel in self.vCategory.voice_channels:
				vConnectedUsers += voiceChannel.members
				# connectedUserIDs = {**connectedUserIDs, **voiceChannel.voice_states.keys()}

		# vcConnectedUsers = []

		# for userID in connectedUserIDs.keys():
		# 	user = self.vGuild.get_member(userID)
		# 	if user == None:
		# 		user = await self.vGuild.fetch_member(userID)
		# 	vcConnectedUsers.append(user)

		BUPrint.Debug(f"Connected user Dict:\nConnectedUser List: {vConnectedUsers}")
		user: discord.Member
		for user in vConnectedUsers:
			try:
				if p_moveToStandby:
					BUPrint.Debug(f"Moving {[user.display_name]} to standby channel ({self.standbyChn.name})")
					await user.move_to(channel=self.standbyChn)
				else:
					BUPrint.Debug(f"Moving {[user.display_name]} to fallback channel ({fallbackChannel.name})")
					await user.move_to(channel=fallbackChannel)
			except Exception as vError:
				BUPrint.LogErrorExc(f"Unable to move member {user.display_name} to Channel (Standby Chn: {p_moveToStandby}).", vError)

class Commander_btnStart(discord.ui.Button):
	def __init__(self, p_commanderParent:Commander):
		self.vCommander:Commander = p_commanderParent
		super().__init__(label="START", emoji="🔘", row=0, style=discord.ButtonStyle.green)

	async def callback(self, p_interaction:discord.Interaction):
		await self.vCommander.StartOperation()
		await p_interaction.response.send_message("Ops started", ephemeral=True)

class Commander_btnDebrief(discord.ui.Button):
	def __init__(self, p_commanderParent:Commander):
		self.vCommander:Commander = p_commanderParent
		super().__init__(label="DEBRIEF", emoji="🗳️", row=0)

	async def callback(self, p_interaction:discord.Interaction):
		pass

class Commander_btnEnd(discord.ui.Button):
	def __init__(self, p_commanderParent:Commander):
		self.vCommander:Commander = p_commanderParent
		super().__init__(label="END", emoji="🛑", row=0)

	async def callback(self, p_interaction:discord.Interaction):
		# End the Ops:
		await self.vCommander.EndOperation()
