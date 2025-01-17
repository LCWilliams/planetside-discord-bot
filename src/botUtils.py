import os
import sys
import datetime
import time
from sys import stderr
from botData.settings import BotSettings, CommandRestrictionLevels, Directories, Messages, Commander, NewUsers, SignUps, UserLib, CommandLimit, Roles, SelfAssignableRoles, Channels, ContinentTrack
from botData.dataObjects import EntryRetention
import botData.utilityData as UtilityData
import traceback
import discord
from discord.ext import commands
# from botData import OperationData



class Singleton(type):
	"""
	# SINGLETON

	Used to ensure singletons via metaclasses.
	"""
	_instances = {}
	def __call__(self, *arguments, **keywords):
		if self not in self._instances:
			self._instances[self] = super().__call__(*arguments, **keywords)
		return self._instances[self]


emptyStrings = [None, "", " ", "_"]
"""# Empty String:
A list of possible 'empty' strings."""


class BotPrinter():
	"""
	BOT PRINTER
	Convenience class containing functions to print various information to console (and/or file).
	"""

	@staticmethod
	def Debug(p_string):
		"""
		DEBUG
		Prints a pre-formatted message to console IF ShowDebug is enabled.
		"""
		if(BotSettings.bDebugEnabled):
			print(f"{UtilityData.ConsoleStyles.timeStyle}[{datetime.datetime.now()}] {p_string}{UtilityData.ConsoleStyles.reset} ")


	@staticmethod
	def Info(p_string):
		"""
		INFO
		Similar to debug, but doesn't depend on ShowDebug to show.
		Should ideally only be used for displaying status as to not flood the console.
		"""
		print(f"{UtilityData.ConsoleStyles.timeStyle}[{datetime.datetime.now()}]{UtilityData.ConsoleStyles.reset} {p_string}")


	@staticmethod
	def LogError(p_string:str, p_titleStr:str = ""):
		"""
		LOG ERROR
		Displays an error to console.

		p_titleString: String shown in alternate colour.
		p_string : The message to show.
		"""
		print(f"{UtilityData.ConsoleStyles.timeStyle}[{datetime.datetime.now()}]{UtilityData.ConsoleStyles.reset} {UtilityData.ConsoleStyles.colourWarn}ERROR | {p_titleStr}{UtilityData.ConsoleStyles.reset} {UtilityData.ConsoleStyles.ColourInfo}{p_string}{UtilityData.ConsoleStyles.reset}", file=sys.stderr)


	@staticmethod
	def LogErrorExc(p_string: str, p_exception: Exception):
		"""
		Same as LOG ERROR, with addition of Exception parameter.
		"""
		print(f"{UtilityData.ConsoleStyles.timeStyle}[{datetime.datetime.now()}]{UtilityData.ConsoleStyles.reset} {UtilityData.ConsoleStyles.colourWarn}ERROR:{UtilityData.ConsoleStyles.reset} {UtilityData.ConsoleStyles.ColourInfo}{p_string} | {UtilityData.ConsoleStyles.reset}{ traceback.print_exc(limit=3)}", file=sys.stderr)





# Used to clear up repeating code
def GetPOSIXTime( pDate: datetime.datetime ):
	"""# Get POSSIX Time
	Returns a POSSIX timestamp from a provided datetime object.."""

	return pDate.strftime("%s")

def GetDiscordTime(pDate: datetime.datetime, pFormat: UtilityData.DateFormat = UtilityData.DateFormat.Dynamic):
	"""# Get Discord Time:
	
	Returns a specially formatted time for discord messages, defaults to dynamic type: "in X days. In 30 minutes" etc..."""
	return f"<t:{GetPOSIXTime(pDate)}{pFormat.value}>"


class FilesAndFolders():
	def SetupFolders():
		"""
		# SETUP FOLDERS:

		Create the folders the bot uses.
		"""
		FilesAndFolders.CreateFolderPath(Directories.savedDefaultsDir)
		FilesAndFolders.CreateFolderPath(Directories.liveOpsDir)
		FilesAndFolders.CreateFolderPath(Directories.userLibrary)
		FilesAndFolders.CreateFolderPath(Directories.userLibraryRecruits)
		FilesAndFolders.CreateFolderPath(Directories.tempDir)
		FilesAndFolders.CreateFolderPath(Directories.runtimeConfigurable)


	def CleanupTemp():
		"""
		# CLEANUP TEMP
		Removes the temp directory. Should only be called during shutdown.
		"""
		if not Directories.bCleanTempOnShutdown:
			return

		if os.path.exists(Directories.tempDir):
			vFiles = FilesAndFolders.GetFiles(Directories.tempDir)
			for fileName in vFiles:
				try:
					os.remove(f"{Directories.tempDir}{fileName}")
				except OSError as vError:
					BotPrinter.LogErrorExc(f"Unable to remove file: {fileName}", vError)



	def DeleteCorruptFile(pDir: str):
		BotPrinter.Info(f"Corrupt file being removed: {pDir}")
		os.remove(pDir)


	def GetFiles(pDir: str, pEndsWith: str = ""):
		vDataFiles: list = []
		for file in os.listdir(pDir):
			if pEndsWith != "" and file.endswith(pEndsWith):
				vDataFiles.append(file)

			elif pEndsWith == "":
				vDataFiles.append(file)

		BotPrinter.Debug(f"Files ending with: {pEndsWith} In: {pDir} found:\n{vDataFiles}")
		return vDataFiles



	def CreateFolderPath(p_folderPath:str):
		"""# Create Folder Path
		Creates the specified folder(s) if it doesn't already exist."""
		BotPrinter.Debug(f"Creating folder {p_folderPath} (if non existant).")
		if (not os.path.exists( p_folderPath ) ):
			try:
				os.makedirs(f"{ p_folderPath }")

			except OSError:
				BotPrinter.LogError(p_titleStr="Failed to create folder(s)!", p_string=p_folderPath)



	def GetOpFullPath(p_opFileName):
		"""
		Convenience function that returns a compiled string of botDir/OpsFolderName/{p_opFileName}.bin
		
		Do not use for DEFAULT ops:  
		They use a different path!
		"""
		return f"{Directories.liveOpsDir}{p_opFileName}.bin"


	def GetLockFilePath(p_opFileName):
		"""
		CONVENIENCE FUNCTION:
		Returns a compiled string (liveOpsDir/p_opFileName.lockFileAffix) of a full path for opFile lock file.
		"""
		return f"{Directories.liveOpsDir}{p_opFileName}{Directories.lockFileAffix}"

	
	def GetLockPathGeneric(p_path):
		"""
		# GET LOCK PATH GENERIC
		Returns a compiled string containing the given path and the lockfile affix. 
		"""
		return f"{p_path}{Directories.lockFileAffix}"


	def IsLocked(p_opLockFile):
		"""# IS LOCKED:
		Checks if the file path given has an associated lock file. to prevent concurrent load/saving.

		## NOTE 
		- Must be given the path to the lock file, and not the file itself.
		- Use the `GetLockFilePath`/`Generic` functions to get this path. 

		## RETURNS: 
		- TRUE if a file is locked.
		- False if a file is lockable.
		"""
		# lockFile = f"{FilesAndFolders.GetOpsFolder}{p_opFileName}{settings.lockFileAffix}"
		if (os.path.exists( p_opLockFile )):
			return True
		else:
			return False


	def GetLock(p_opLockFile):
		"""
		GET LOCK:
		Creates a lock for a file.

		NOTE: Will wait until any existing lock stops existing before creating.
		"""
		BotPrinter.Debug(f"Getting lock file for: {p_opLockFile}")
		attempsLeft = 5
		while FilesAndFolders.IsLocked(p_opLockFile):
			if attempsLeft > 0:
				time.sleep(0.2)
				attempsLeft -= 1
			else:
				BotPrinter.Info(f"Attempted to get lock on file {p_opLockFile}, but ran out of attempts.")
				return False

		# No lock file exists!
		BotPrinter.Debug(f"	-> Creating lock file... ")
		return FilesAndFolders.CreateLock(p_opLockFile)


	def CreateLock(p_opLockFile):
		"""
		CREATE LOCK:

		NOTE Should not be called manually, use GetLock instead!
		
		Creates a lock file for the given Ops file.  

		RETURNS
		True - On success.
		False - On Failure (exception)
		"""
		
		try:
			open(p_opLockFile, 'a').close()
			return True
		except OSError as vError:
			BotPrinter.LogErrorExc("Failed to create LOCK file", vError)
			return False


	def ReleaseLock(p_fileToRelease:str) -> discord.guild.Guild:
		"""
		RELEASE LOCK:

		Removes a lock file for the given File.
		Should be called every time GETLOCK is called.
		
		RETURNS
		True - On success (or file doens't exist)
		False - On Failure (exception)
		"""
		BotPrinter.Debug(f"Releasing lock for {p_fileToRelease}")

		if not p_fileToRelease.__contains__( Directories.lockFileAffix ):
			BotPrinter.Debug("	-> File specified isn't a lock file!")
			return False

		if(FilesAndFolders.IsLocked(p_fileToRelease)):
			try:
				os.remove(p_fileToRelease)
				BotPrinter.Debug(f"	-> Lock file released!")
				return True
			except OSError as vError:
				BotPrinter.LogErrorExc("Failed to remove LOCK file", vError)
				return False
		BotPrinter.Debug("	-> No lock file present")
		return True


def GetGuildNF(p_botRef: commands.Bot) -> discord.Guild:
	"""
	# GET GUILD: No Fetch.
	Similar to GetGuild, but does not fetch if no guild found.
	
	### RETURNS
	The `discord.guild` using the id specified in settings or `none` if not found.
	"""
	BotPrinter.Debug("Getting Guild from ID.")
	try:
		guild = p_botRef.get_guild( BotSettings.discordGuild )
		if guild != None:
			return guild

	except discord.Forbidden as vError:
		BotPrinter.LogErrorExc("Bot has no access to this guild!", p_exception=vError)
		return None

	except discord.HTTPException:
		BotPrinter.LogErrorExc("Unable to get guild.", p_exception=vError)
		return None


async def GetGuild(p_BotRef : commands.Bot):
	"""
	# GET GUILD:
	
	`p_BotRef`: A reference to the bot.

	RETURNS: a discord.Guild using the ID from settings.

	Tries get first, then fetch.
	"""
	BotPrinter.Debug("Getting Guild from ID.")
	try:
		guild = p_BotRef.get_guild(BotSettings.discordGuild )
		if guild != None:
			return guild

		BotPrinter.Debug(f"	-> Failed to GET, attempting fetch instead.")
		guild = await p_BotRef.fetch_guild( BotSettings.discordGuild)
		if guild == None:
			BotPrinter.Info("Unable to fetch guild!  Ensure you have the right ID.")
			return None
	
		BotPrinter.Debug(f"Guild found with Fetch!  Chunked: {guild.chunked}")
		return guild

	except discord.Forbidden as vError:
		BotPrinter.LogErrorExc("Bot has no access to this guild!", p_exception=vError)
		return None

	except discord.HTTPException:
		BotPrinter.LogErrorExc("Unable to get guild.", p_exception=vError)
		return None




async def UserHasCommandPerms(p_callingUser:discord.Member, p_requiredLevel:CommandRestrictionLevels, p_interaction: discord.Interaction):
	"""
	# USER HAS VALID PERMS
	Checks if the user provided has any role within restriction level.

	NOTE: If `settings.bForceRoleRestrictions` is false, this always returns true.
	"""
	if not BotSettings.bForceRoleRestrictions:
		return True

	bHasPermission = UserHasPerms(p_callingUser, p_requiredLevel)
	
	if not bHasPermission and p_interaction != None:
		await p_interaction.response.send_message(Messages.invalidCommandPerms, ephemeral=True)
	
	return bHasPermission



def UserHasPerms(p_user:discord.Member, p_requiredLevel:CommandRestrictionLevels):
	"""
	# USER HAS PERMS
	Similar to UserHasCommandPerms, except does not check `settings.bForceRoleRestrictions`.
	Expected to be used outside of command/button checks, but still utilise the `CommandRestrictionLevels`.
	"""
	for role in p_user.roles:
		if str(role.id) in p_requiredLevel.value or role.name in p_requiredLevel.value:
			return True
	
	return False

	


class ChannelPermOverwrites():
	"""
	# CHANNEL PERM OVERWRITES
	A class containing overwrite variables relating to the 4 restrictLevels, one `invisible` variable for hiding channels and a single function to set them (ideally on startup!).
	"""
	level0 = {}
	level1 = {}
	level2 = {}
	level3 = {}
	level3_readOnly = {}
	invisible = {}
	def __init__(self) -> None:
		pass
	
	async def Setup(p_botRef:commands.Bot):
		guild = await p_botRef.fetch_guild(BotSettings.discordGuild)
		roles = await guild.fetch_roles()
		# Defaults:

		ChannelPermOverwrites.level3[guild.default_role] = discord.PermissionOverwrite(read_messages=False)

		ChannelPermOverwrites.level2[guild.default_role] = discord.PermissionOverwrite(read_messages=False)

		ChannelPermOverwrites.level1[guild.default_role] = discord.PermissionOverwrite(read_messages=False)

		ChannelPermOverwrites.level0[guild.default_role] = discord.PermissionOverwrite(read_messages=False)

		role : discord.Role
		for role in roles:
			# SETUP LEVEL 3
			if role.name in CommandRestrictionLevels.level3.value or role.id in CommandRestrictionLevels.level3.value:
				ChannelPermOverwrites.level3[role] = discord.PermissionOverwrite(
					read_messages=True,
					send_messages=True,
					connect=True
				)

				ChannelPermOverwrites.invisible[role] = discord.PermissionOverwrite(
					read_messages=False
				)

				ChannelPermOverwrites.level3_readOnly[role] = discord.PermissionOverwrite(
					read_messages=True,
					send_messages=False
				)


			# SEUP LEVEL 2
			if role.name in CommandRestrictionLevels.level2.value or role.id in CommandRestrictionLevels.level2.value:
				ChannelPermOverwrites.level2[role] = discord.PermissionOverwrite(
					read_messages=True,
					send_messages=True,
					connect=True
				)


			# SEUP LEVEL 1
			if role.name in CommandRestrictionLevels.level1.value or role.id in CommandRestrictionLevels.level1.value:
				ChannelPermOverwrites.level1[role] = discord.PermissionOverwrite(
					read_messages=True,
					send_messages=True,
					connect=True
				)


			# SEUP LEVEL 0
			if role.name in CommandRestrictionLevels.level0.value or role.id in CommandRestrictionLevels.level0.value:
				ChannelPermOverwrites.level0[role] = discord.PermissionOverwrite(
					read_messages=True,
					send_messages=True,
					connect=True
				)

		BotPrinter.Info("ChannelPermOverwrites have been configured!")



def SplitStrToSegments(p_string:str, p_limit:int = 1024, p_maxSegments: int = 0) -> list[str]:
	"""# Split String to Segments
	Takes a string (typically created from a list, with newline seperators) and splits it into segments.

	Typically used in cases where a text body is too large.

	NOTE: 	Embed value max limit is 1,024.
	NOTE:	Message max limit is 2,000

	## PARAMS
	- `p_string` -  The string to split up.
	- `p_limit` - The maximum length of each segment.
	- `p_maxSegments` - The maximum number of segments to split into.
	"""

	strAsArray = p_string.split("\n")

	segments:list[str] = []

	currentSegment = ""
	for currentLine in strAsArray:

		if len(currentSegment) + len(currentLine) > p_limit:
			segments.append(f"{currentSegment}")

			if len(segments) == p_maxSegments:
				break

			currentSegment = f"{currentLine}\n"

		else:
			currentSegment += f"{currentLine}\n"
			
	# Make sure to append the currently active segment, otherwise its omitted
	segments.append(currentSegment)

	if len(segments) == 0 and len(currentSegment) != 0:
		return currentSegment
	else:
		return segments
	


def EllipsiseStringArrayToSize(p_string:str, p_size:int, p_ellipsiseStart:bool = True) -> str:
	"""# Ellipsise String Array to Size
	Takes a string (typically created from an array, and contains newlines) and returns an ellipsised string when it exceeds the specified size.

	## PARAMETRS
	- `p_string` : the string to modify
	- `p_size`: The maximum size of the output string. The resulting string will always be 10 characters less than this for the ellipses + \n and possible number count.
	- `p_ellipsiseStart`: True to put ellipses at the start, false for at the end.
	"""
	maxSize = p_size - 15
	newString = ""
	stringArray = p_string.split("\n")
	linesAdded = 0

	if p_ellipsiseStart:
		# Start from the end.
		for line in reversed(stringArray):
			if len(line) + len(newString) < maxSize:
				newString = f"{line}\n{newString}"
				linesAdded += 1
			else:
				newString = f"...\n{newString}"
				break

	else:
		for line in stringArray:
			if len(line) + len(newString) < maxSize:
				newString = f"{line}\n{newString}"
				linesAdded += 1
			else:
				newString = f"{newString}\n..."
				break
			
	if BotSettings.bEllipseArrayShowsCount:
		newString = newString.replace("...", f"...({len(stringArray) - linesAdded })")

	return newString



	

def EllipseStringToSize(p_string:str, p_size:int, p_ellipiseStart:bool = True) -> str:
	"""# Elispe String to Size:
	Takes a string and reduces it down to the size specified, placing a ellipses at the start or end to indicate missing text.

	## PARAMETRS
	- `p_string` : the string to modify
	- `p_size`: The maximum size of the output string. The resulting string will always be 3 characters less than this for the ellipses & possible number count.
	- `p_ellipsiseStart`: True to put ellipses at the start, false for at the end.
	"""
	maxSize = p_size - 15
	newString = ""

	if p_ellipiseStart:
		# Start from end
		for character in ReverseString(p_string):
			if len(newString) < maxSize:
				newString += character
			else:
				newString = f"...\n{ReverseString(newString)}"
				break

	else:
		# Start from beginning
		for character in p_string:
			if len(newString) < max:
				newString += character
			else:
				newString = f"{newString}\n..."
				break
			
	if BotSettings.bEllipseArrayShowsCount:
		newString = newString.replace("...", f"...({ len(p_string) - len(newString)})")

	return newString



def ReverseString(p_string:str) -> str:
	"""# Reverse String
	As stated, reverses the order of a string.
	"""
	reversedStr = p_string[::-1]
	return reversedStr

		



def PrintSettings(bGetOnly = False):
	"""
	# PRINT SETTINGS
	To keep the settings file clean and easier to read, the printing is moved here.

	Specify bGetOnly as TRUE to get the settings as a string instead.
	"""
	vString = "\n"


	vString += "\nBOT DIRECTORY SETTINGS\n"
	vString += f"	> Prefix Dir :	{Directories.prefixDir}\n"
	vString += f"	> LiveOps Dir:	{Directories.liveOpsDir}\n" 
	vString += f"	> DefaultsDir:	{Directories.savedDefaultsDir}\n" 
	vString += f"	> UserLib Dir:	{Directories.userLibrary}\n"
	vString += f"	> RecruitsDir:	{Directories.userLibraryRecruits}\n"
	vString += f"	> RuntimeDir :	{Directories.runtimeConfigurable}\n"
	vString += f"	> LockFile Affix:	{Directories.lockFileAffix} | Retries: {Directories.lockFileRetry}\n"
	vString += f"	> Feedback Prefix:	{Directories.feedbackPrefix}\n"
	vString += f"	> Clean Temp Every:	{Directories.cleanTempEvery} hours ({Directories.cleanTempEvery/24} days)\n"
	vString += f"	> [{Directories.bCleanTempOnShutdown}] Clean Temp On Shutdown:\n"


	vString += "\nFEATURES\n"
	vString += f"	> [{BotSettings.botFeatures.BotAdmin}] Bot Admin\n"
	vString += f"	> [{BotSettings.botFeatures.NewUser}] New User\n"
	vString += f"	> [{BotSettings.botFeatures.Operations}] Operations\n"
	vString += f"	> [{BotSettings.botFeatures.UserLibrary}] User Library\n"
	vString += f"		>> [{BotSettings.botFeatures.userLibraryInboxAdmin}] Inbox System | [{BotSettings.botFeatures.userLibraryInboxAdmin}] Inbox Admin | [{BotSettings.botFeatures.UserLibraryFun}] Fun Features\n"
	vString += f"	> [{BotSettings.botFeatures.UserRoles}] User Roles\n"
	vString += f"	> [{BotSettings.botFeatures.chatUtility}]  Chat Utility\n"
	vString += f"	> [{BotSettings.botFeatures.ForFunCog}] For Fun Cog\n"
	vString += f"	> [{BotSettings.botFeatures.continentTracker}] PS2 Continent Tracker\n"


	vString += "\nGENERAL BOT SETTINGS\n"
	vString += f"	> [{BotSettings.bDebugEnabled}] Debug Enabled \n"
	token = BotSettings.discordToken[:5] # Always hide most of the token; shows JUST the first 5 characters.
	vString += f"	> DiscordToken:	{token}...\n"
	vString += f"	> DiscordGuild:	{BotSettings.discordGuild}\n"
	token = BotSettings.ps2ServiceID[:5]
	vString += f"	> PS2ServiceID:	{token}...\n"
	vString += f"	> BotDirectory:	{BotSettings.botDir}\n"
	vString += f"	> [{BotSettings.bBotAdminCanPurge}] Can Purge BotAdmin\n"
	vString += f"	> [{BotSettings.bEllipseArrayShowsCount}] Ellipses Shows Count\n"
	if BotSettings.errorOutput == stderr:
		vString += f"	> Error Output:	stderr\n"
	else:
		vString += f"	> Error Output:	{BotSettings.errorOutput}\n"
	vString += f"	> [{BotSettings.bCheckValues}] Sanity Check Values\n"
	vString += f"\n	> Force Role Restrictions: {BotSettings.bForceRoleRestrictions}\n"
	vString += f"	> Level 0:	{Roles.roleRestrict_level_0}\n"
	vString += f"	> Level 1:	{Roles.roleRestrict_level_1}\n"
	vString += f"	> Level 2:	{Roles.roleRestrict_level_2}\n"
	vString += f"	> Level 3:	{Roles.roleRestrict_level_3}\n"


	vString += "\nROLES\n"
	vString += f"	> Recruit ID:		{Roles.recruit}\n"
	vString += f"	> Promoted Role ID:	{Roles.recruitPromotion}\n"
	vString += f"	> Auto Assign on Accept:{Roles.autoAssignOnAccept}\n"
	if BotSettings.botFeatures.UserRoles:
		vString += f"	> Filename Affix: {SelfAssignableRoles.fileNameAffix}\n"
		vString += f"	> Deliminator: {SelfAssignableRoles.deliminator}\n"


	vString += "\nCHANNELS\n"
	vString += f"	> Bot Admin:	{Channels.botAdminID}\n"
	vString += f"	> General:	{Channels.generalID}\n"
	vString += f"	> PS2 Text:	{Channels.ps2TextID}\n"
	vString += f"	> Facility Control:	{Channels.ps2FacilityControlID}\n"
	vString += f"	> Continent Status:	{Channels.ps2ContinentNotifID}\n"
	vString += f"	> Rules:	{Channels.ruleID}\n"
	vString += f"	> Gate:		{Channels.gateID}\n"
	vString += f"	> Voice Fallback:{Channels.voiceFallback}\n"
	vString += f"	> Event Moveback:{Channels.eventMovebackID}\n"
	vString += f"	> Protected Categories:\n		> {Channels.protectedCategoriesID}\n"
	vString += f"	> Quotes:	{Channels.quoteID}\n"
	vString += f"	> Schedule:	{Channels.scheduleID}\n"
	vString += f"	> Other Games:	{Channels.otherGameCatID}\n"



	vString += f"\nCOMMAND LIMITS\n"
	vString += f"	> Validate New User: {CommandLimit.validateNewuser.name}\n"
	vString += f"	> User Roles: {CommandLimit.userRoles.name}\n"
	vString += f"	> Op Manager:	{CommandLimit.opManager.name}\n"
	vString += f"	> Op Commander: {CommandLimit.opCommander.name}\n"
	vString += f"	> User Library: {CommandLimit.userLibrary.name}\n"
	vString += f"	> User Library Admin: {CommandLimit.userLibraryAdmin.name}\n"
	vString += f"	> Chat Utilities: {CommandLimit.chatUtilities.name}\n"
	vString += f"	> Continent Tracker: {CommandLimit.continentTracker.name}\n"
	vString += f"	> Continent Tracker Admin: {CommandLimit.continentTrackerAdmin.name}\n"



	vString += "\nNEW USER SETTINGS\n"
	vString += f"	> Rule Message:		{NewUsers.ruleMsgID}\n"
	vString += f"	> [{NewUsers.bShowAddRolesBtn}] Show AddRoles Button\n"
	vString += f"	> [{NewUsers.bCreateLibEntryOnAccept}] Create Library Entry on Accept\n"
	vString += f"	> [{NewUsers.bLockPS2CharOnAccept}] AutoLock PS2 Character on Accept\n"
	vString += f"	> [{NewUsers.bPurgeGate}] Purge Gate\n"
	vString += f"\n	> Warnings: Discord Account age: {NewUsers.newAccntWarn} months\n"
	vString += f"	> Warnings: Outfit Rank (Ord): {NewUsers.outfitRankWarn}\n"



	vString += "\nOP COMMANDER SETTINGS\n"
	vString += f"	> [{Commander.bAutoStartEnabled}] Auto Start\n"
	vString += f"	> Auto prestart:	{Commander.autoPrestart} minutes\n"
	vString += f"	> [{Commander.bTrackingIsEnabled}] Tracking Enabled\n"
	vString += f"	> Tracking Interval:	{Commander.dataPointInterval} seconds\n"
	vString += f"	> Marked Present:	{Commander.markedPresent.name}\n"
	vString += f"	> [{Commander.bAutoAlertsEnabled}] Auto Alerts\n"
	vString += f"	> Auto Alert count:	{Commander.autoAlertCount}\n"
	vString += f"	> [{Commander.bAutoMoveVCEnabled}] Auto Move VC\n"
	vString += f"	> Default Channels: {Commander.defaultChannels}\n"



	vString += "\nCONTINENT TRACKER SETTINGS\n"
	vString += f"	> [{BotSettings.botFeatures.continentTracker}] Enabled\n"
	if BotSettings.botFeatures.continentTracker:
		vString += f"	> [{ContinentTrack.bSaveOnShutdown}] Save on Shutdown\n"
		vString += f"	> World ID: {ContinentTrack.worldID}\n"
		vString += f"	> ContinentTracker Reconnection time: {ContinentTrack.reconnectionTime}\n"
		vString += f"	> Message type on LOCK events: {ContinentTrack.contLockMessageType.name}\n"
		vString += f"	> Message type on OPEN events: {ContinentTrack.contUnlockMessageType.name}\n"
		vString += f"	> Anti-Spam: Allowed posts: {ContinentTrack.antiSpamAllowedPosts}\n"
		vString += f"	> Anti-Spam: Minimal interval time: {ContinentTrack.antiSpamMinimalTime}\n"
		vString += f"	> [{ContinentTrack.bAlertCommanders}] Alert Commanders\n"
		vString += f"	> [{ContinentTrack.bMonitorFacilities}] Monitor Facility Captures\n"
		if ContinentTrack.bMonitorFacilities:
			vString += f"	> Outfit to monitor: {ContinentTrack.facilityMonitorOutfitID}\n"


	vString += "\nSIGN UP SETTINGS\n"
	vString += f"	> [{SignUps.bAutoParseSchedule}] Parse Schedule\n"
	vString += f"	> Parse Schedule timeout: {SignUps.autoParseTimeout}\n"
	vString += f"	> [{SignUps.bAutoRemoveOutdated}] Autoremove Outdated\n"
	vString += f"	> Signup Cat  : {SignUps.signupCategory}\n"
	vString += f"	> Resign Icon : {SignUps.resignIcon}\n" 
	vString += f"	> Reserve Icon: {SignUps.reserveIcon}\n"
	vString += f"	> [{SignUps.bResignAsButton}] Resign As Button\n" 
	vString += f"	> [{SignUps.bAutoPrestartEnabled}] Auto Prestart\n"
	vString += f"	> [{SignUps.bShowOptsInFooter}] Show Opts in Footer\n"



	vString += "\nUSER LIBRARY SETTINGS\n"
	vString += f"	> [{UserLib.bEnforcePS2Rename}] Enforce PS2 Names\n"
	vString += f"	> [{UserLib.bEnableSpecialUsers}] Special Users\n"
	vString += f"	> [{UserLib.bEnableInbox}] User Inbox Enabled\n"
	vString += f"	> [{UserLib.bShowJumpButtonsForGetEvents}] Show jump buttons for GetEvents\n"
	vString += f"	> [{UserLib.bCommanderCanAutoCreate}] Commander Create Entry\n"
	vString += f"	> [{UserLib.bUserCanSelfCreate}] User Self Create\n"
	vString += f"	> Max Saved Events:	{UserLib.maxSavedEvents}\n"
	vString += f"	> [{UserLib.bAutoPromoteEnabled}] AutoPromote Users\n"
	vString += f"	> AutoPromote Rules:	{UserLib.autoPromoteRules}\n"
	vString += f"	> AutoPromote Times:	{UserLib.autoQueryRecruitTime}\n"
	vString += f"	> Max Session Previews:	{UserLib.sessionPreviewMax}\n"
	vString += f"	> Max Sessions Browser:	{UserLib.sessionMaxPerPage}\n"
	vString += f"	> [{UserLib.bRemoveEntryOnLeave}] Remove Entry on leave\n"
	vString += f"	> [{UserLib.bRemoveSpecialEntryOnLeave}] Remove Special Entry on leave\n"
	vString += f"	> Library Data Memory Retention: {UserLib.entryRetention.name}\n"
	if UserLib.entryRetention == EntryRetention.unloadAfter:
		vString += f"		> Unload After: {UserLib.entryRetention_unloadAfter} | Check Interval {UserLib.entryRetention_checkInterval}\n"
	vString += f"	> [{UserLib.sleeperRules.bIsEnabled}] Inactivity Check\n"
	if UserLib.sleeperRules.bIsEnabled:
		vString += f"	> {UserLib.sleeperRules}" # __repr__ return has a new line at the end.
		vString += f"	> Sleeper Check Time: {UserLib.sleeperCheckTime}\n"



	if bGetOnly:
		return vString
	else:
		BotPrinter.Info(vString)