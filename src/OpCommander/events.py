"""
OP COMMANDER - EVENTS:
Deals with live ops tracking by use of events.
"""
from __future__ import annotations

from auraxium.event import EventClient, Trigger, PlayerLogin, PlayerLogout, GainExperience, VehicleDestroy
from auraxium.ps2 import Character, Vehicle, MapRegion
from auraxium import event

from datetime import datetime, timezone

from botUtils import BotPrinter as BUPrint
from botUtils import GetDiscordTime
from botData.utilityData import DateFormat

from botData.settings import ForFun
from botData.dataObjects import EventPoint, Participant, EventID, PS2SessionKDA, PS2SessionEngineer, PS2SessionMedic, ForFunData, ForFunVehicleDeath, FacilityData

from random import choice


class OpsEventTracker():
	"""
	# OPS EVENT TRACKER
	A class which handles the tracking of a planetside 2 track enabled event.

	Must be passed a participant list before starting!
	"""
	def __init__(self, p_aurClient: EventClient) -> None:
		self.auraxClient = p_aurClient
		self.updateParentFunction = None
		self.parentSendForFunVehicleDeath = None

		self.participants:list[Participant] = []
		self.triggerList:list[Trigger] = []
		self.loginTrigger : Trigger = None
		self.logOutTrigger : Trigger = None

		# LAST FACILITY DEFENDED/CAPTURED
		self.lastFacilityDefended:FacilityData = None
		self.lastFacilityCaptured:FacilityData = None
		self.facilityFeed:list[str] = [] # Feed of facility capture/defends with dates.

		self.forFunVehicleDeaths: list[ForFunVehicleDeath]

		self.eventPoints: list[EventPoint] = []
		self.currentEventPoint:EventPoint = None
		BUPrint.Info("Ops Event Tracker initialised!")



	def Start(self):
		"""
		# START
		Starts the tracking and locks in the participants.
		"""
		# Redundancy, the event should be closed without ever calling start if there's no participants.
		if self.participants.__len__() == 0:
			BUPrint.LogError(p_titleStr="OPS EVENT TRACKER | ", p_string="Not starting tracker, no participants!")
			return
		
		self.CreateTriggers()
		self.currentEventPoint = EventPoint( timestamp=datetime.now(timezone.utc).time(), activeParticipants=len(self.participants) )

		# Create KDA object.  Since every participant is capable of obtaining this; it is created for everyone, unlike the role specific objects.
		for participant in self.participants:
			participant.userSession.kda = PS2SessionKDA()
		
		
		BUPrint.Info("Full event Tracking has started!")



	async def Stop(self):
		"""# STOP
		Stops the event tracker.
		"""
		await self.auraxClient.close()



	async def CreateLoginTriggers(self, p_newParticipantList:list[Participant]):
		"""# CREATE LOGIN TRIGGERS
		Seperate from `Create Triggers` in that this is specifically for login and logout events,
		and is added to the client immediately- intended to be called from the commander after the participant list has changed.
		"""
		self.participants = p_newParticipantList
		BUPrint.Debug(f"Creating Login/Out Triggers, for :{self.participants}")

		if self.loginTrigger != None:
			BUPrint.Debug("Removing old Login trigger...")
			self.auraxClient.remove_trigger(self.loginTrigger, keep_websocket_alive=True)
		
		if self.logOutTrigger != None:
			BUPrint.Debug("Removing old LogOut trigger...")
			self.auraxClient.remove_trigger(self.logOutTrigger, keep_websocket_alive=True)

		if len(self.participants) == 0:
			BUPrint.Debug("Participant list is empty. Not creating login triggers.")
			return

		vCharList:list[int] = []
		for participant in self.participants:
			if participant.ps2Char != None:
				BUPrint.Debug(f"	> {participant.ps2Char} added to trigger character list.")
				vCharList.append(participant.ps2Char.id)

				# Check status if player, incase they were already online when causing an update.
				if not participant.bPS2Online:
					participant.bPS2Online = await participant.ps2Char.is_online()

		

		# Create new Login & Logout trigger
		self.loginTrigger = Trigger( event="PlayerLogin", characters=vCharList, action=self.UpdatePlayerLogin)
		self.logOutTrigger = Trigger( event="PlayerLogout", characters=vCharList, action=self.UpdatePlayerLogout)

		self.auraxClient.add_trigger( self.loginTrigger )
		self.auraxClient.add_trigger( self.logOutTrigger )



	async def UpdatePlayerLogin(self, p_loginEvent: PlayerLogin):
		await self.UpdatePlayerStatus(p_loginEvent.character_id, True)



	async def UpdatePlayerLogout(self, p_logoutEvent: PlayerLogout):
		await self.UpdatePlayerStatus(p_logoutEvent.character_id, False)




	async def UpdatePlayerStatus(self, p_charID:int, p_isLoggedIn:bool):
		"""# UPDATE PLAYER STATUS
		Since Login and Logout are individual events,
		this is a convenience function to be called from the respective individual functions.
		"""
		for participant in self.participants:
			if participant.ps2Char.id == p_charID:
				participant.bPS2Online = p_isLoggedIn
				BUPrint.Debug(f"Participant: {participant.discordUser.display_name} updated.  Online [{p_isLoggedIn}]")
				await self.updateParentFunction()
				return
		BUPrint.Debug("Player Status attempted update but participant not found")



	def NewEventPoint(self):
		"""# NEW EVENT POINT
		Moves the current event point into the point list, and sets a new one.
		"""
		self.eventPoints.append(self.currentEventPoint)
		
		stillOnline = 0
		for participant in self.participants:
			stillOnline += int(participant.bPS2Online)
		
		self.currentEventPoint = EventPoint(timestamp = datetime.now(timezone.utc).time(), activeParticipants = stillOnline)

		BUPrint.Debug(f"New Event Point: TimeStamp:{datetime.now(timezone.utc).time()}, Active Participants: {stillOnline}")




	def CreateTriggers(self):
		""" # CREATE TRIGGERS
		Creates and sets the triggers for the event.
		"""
		playerCharacters = []

		if len(self.participants) == 0:
			BUPrint.Debug("Empty participant list. Not creating full triggers.")
			return

		# Iterate through participants to get their PS2Char objects.
		for participant in self.participants:
			if participant.ps2Char != None:
				playerCharacters.append(participant.ps2Char.id)



		# ENGINEER
		# Squad Vehicle repairs
		for eventID in EventID.eng_vehicleRepair:
			self.auraxClient.add_trigger(
				Trigger(
					action=self.EngSquadVehicleRepair,
					characters=playerCharacters,
					event=GainExperience.filter_experience(eventID)
				)
			)

		# Squad Resupply
		self.auraxClient.add_trigger(
			Trigger(
				action=self.EngSquadResupply,
				characters=playerCharacters,
				event=GainExperience.filter_experience(EventID.eng_resupply)
			)
		)


		# MEDIC
		# Squad heal
		self.auraxClient.add_trigger(
			Trigger(
				action=self.MedicSquadHeal,
				characters=playerCharacters,
				event=GainExperience.filter_experience(EventID.med_heal)
			)
		)

		# Squad Revive
		self.auraxClient.add_trigger(
			Trigger(
				action=self.MedicSquadRevive,
				characters=playerCharacters,
				event=GainExperience.filter_experience(EventID.med_revive)
			)
		)		


		# NON-SPECIFIC:

		# Kill
		self.auraxClient.add_trigger(
			Trigger(
				action=self.GotKill,
				characters=playerCharacters,
				event=GainExperience.filter_experience(EventID.kill)
			)
		)

		self.auraxClient.add_trigger(
			Trigger(
				action=self.Died,
				characters=playerCharacters,
				event="death"
			)
		)


	def GetMatchingParticipant(self, p_playerCharID:int):
		"""
		# GET MATCHING PARTICIPANTS
		Gets the `Participant` object for the matching player character.
		
		None if not found, though this occurance shouldn't happen. 
		"""
		for participant in self.participants:
			if participant.ps2Char.id == p_playerCharID:
				return participant 
		
		BUPrint.LogError(p_titleStr="Invalid participant given")
		return None


	def GetForFunVehicleEvent(self, p_killerID, p_vehicleID):
		for vehicleEvent in self.forFunVehicleDeaths:
			if vehicleEvent.driverCharID == p_killerID and vehicleEvent.driverVehicleID == p_vehicleID:
				return vehicleEvent

		# No existing event
		newEvent = ForFunVehicleDeath(driverCharID=p_killerID, driverVehicleID=p_vehicleID)
		self.forFunVehicleDeaths.append(newEvent)

		return newEvent



	def SetLatestFacilityUpdate(self):
		pass

# # # # # EVENT FUNCTIONS

	# def PlayerDeath(self, )

	def EngSquadVehicleRepair(self, p_event: event.GainExperience):
		""" # ENGINEER SQUAD VEHICLE REPAIR:
		Event function for when a player gains experience from repairing a squad vehicle.
		"""
		vParticipant = self.GetMatchingParticipant(p_event.character_id)
		
		if vParticipant == None:
			return

		if vParticipant.userSession.engineerData == None:
			vParticipant.userSession.engineerData = PS2SessionEngineer()

		# Set operatons Event Point:
		self.currentEventPoint.repairs += p_event.amount
		
		# Set participants data:
		vParticipant.userSession.engineerData.repairScore += p_event.amount
	

	def EngSquadResupply(self, p_event: event.GainExperience):
		""" # ENGINEER SQUAD RESUPPLY:
		Event function for when a player gains experience from repairing a squad vehicle.
		"""
		vParticipant = self.GetMatchingParticipant(p_event.character_id)
		
		if vParticipant == None:
			return

		if vParticipant.userSession.engineerData == None:
			vParticipant.userSession.engineerData = PS2SessionEngineer()

		# Set operatons Event Point:  (none)
		# self.currentEventPoint.resupply += p_event.amount
		
		# Set participants data:
		vParticipant.userSession.engineerData.resupplyScore += p_event.amount


	def MedicSquadHeal(self, p_event: event.GainExperience):
		"""# MEDIC SQUAD HEAL
		Event function for when a player gains experience from healing a squadmate.
		"""
		vParticipant = self.GetMatchingParticipant(p_event.character_id)
		
		if vParticipant == None:
			return

		if vParticipant.userSession.medicData == None:
			vParticipant.userSession.medicData = PS2SessionMedic()

		# Set operatons Event Point: (None)
		# self.currentEventPoint.revives += p_event.amount
		
		# Set participants data:
		vParticipant.userSession.medicData.heals += p_event.amount


	def MedicSquadRevive(self, p_event: event.GainExperience):
		"""# MEDIC SQUAD REVIVE
		Event function for when a player gains experience from reviving a squadmate.
		"""
		vParticipant = self.GetMatchingParticipant(p_event.character_id)
		
		if vParticipant == None:
			return

		if vParticipant.userSession.medicData == None:
			vParticipant.userSession.medicData = PS2SessionMedic()

		# Set operatons Event Point:
		self.currentEventPoint.revives += 1
		
		# Set participants data:
		vParticipant.userSession.medicData.revives += 1
		vParticipant.userSession.score += p_event.amount


	def GotKill(self, p_event: event.GainExperience):
		"""# GOT KILL:
		Function to run when a player has gotten a kill.
		"""
		self.currentEventPoint.kills += 1

		vParticipant = self.GetMatchingParticipant(p_event.character_id)

		vParticipant.userSession.score += p_event.amount
		vParticipant.userSession.kda.kills += 1



	async def Died(self, p_event: event.Death):
		"""# DIED
		Function to run when a player died."""
		self.currentEventPoint.deaths += 1

		vParticipant = self.GetMatchingParticipant(p_event.character_id)
		vAttacker = self.GetMatchingParticipant(p_event.attacker_character_id)

		BUPrint.Debug(f"		->{vParticipant.ps2Char} died.")

		# Increment death total, to account for self-caused deaths and non-player caused deaths (pain fields/fall damage) and avoid needing to caclulate later.
		vParticipant.userSession.kda.deathTotal += 1

		# Attacker is squadmate.
		if vAttacker != None:
			BUPrint.Debug(f"{vParticipant.ps2Char} killed by squadmate: {vAttacker.ps2Char}")

			vParticipant.userSession.kda.deathBySquad += 1
			vAttacker.userSession.kda.killedSquad += 1

			if ForFun.bBroadcastPS2VehicleDeath or ForFun.bPS2VehicleDeathFunEvent:
				if p_event.attacker_vehicle_id != 0:

					vFunEvent = self.GetForFunVehicleEvent(p_event.attacker_character_id, p_event.attacker_vehicle_id)

					# GALAXY:
					if p_event.attacker_vehicle_id == 11:

						vParticipant.userSession.funEvents.append( choice(ForFunData.galaxyDeath).replace("_USER"), vAttacker.discordUser.mention )
						
						if vFunEvent.message == "":
							vFunEvent.message = choice(ForFunData.galaxyDeathBy)
					

					# SUNDERER
					elif p_event.attacker_vehicle_id == 1:

						vParticipant.userSession.funEvents.append( choice(ForFunData.partyBusDeath).replace("_USER"), vAttacker.discordUser.mention )

						if vFunEvent.message == "":
							vFunEvent.message = choice(ForFunData.partyBusDeathBy)
			
			# Do not need to continue.
			return


		# Determine if killer character is allied or an enemy.
		vAttackerPS2Char = await self.auraxClient.get_by_id(Character, p_event.attacker_character_id)
		if vAttackerPS2Char.faction_id == 2: # NC
			vParticipant.userSession.kda.deathByAllies += 1
		else:
			vParticipant.userSession.kda.deathByEnemies += 1

		# Potential to do enemy character death by name fun events here.

	async def FacilityCapture(self, p_event: event.PlayerFacilityCapture):
		"""# FACILITY CAPTURE
		Function to call when a player participates in a facility capture."""
		vFacility:MapRegion = await MapRegion.get_by_id(p_event.facility_id, self.auraxClient)
		
		# Used to avoid repetition later.
		vNewFacilityData = FacilityData(
				facilityID=p_event.facility_id, 
				timestamp=datetime.now(tz=timezone.utc),
				facilityObj = vFacility,
				participants=1
			)

		
		# First facility capture.
		if self.lastFacilityCaptured == None:
			self.lastFacilityCaptured = vNewFacilityData
			self.facilityFeed.append( f" {GetDiscordTime(vNewFacilityData.timestamp), DateFormat.TimeShorthand} | {vFacility.facility_name} | {vFacility.facility_type}" )
			self.currentEventPoint.captured += 1
			await self.updateParentFunction()
			return

		
		
		# Existing/Current facility capture.  Ensures repeated calls (from each character) don't inflate the stats.
		# Also ensures if the facility captured is the last one captured and is being recaptured.
		if self.lastFacilityCaptured.facilityID == p_event.facility_id:
			timeDifference = self.lastFacilityCaptured.timestamp - datetime.now()
			if  timeDifference.total_seconds() > 900: # 15 minutes
				BUPrint.Debug("Time difference is greater than 15 minutes.  Recaptured last capture.")
				self.lastFacilityCaptured = vNewFacilityData
				self.facilityFeed.append( f" {GetDiscordTime(vNewFacilityData.timestamp), DateFormat.TimeShorthand} | {vFacility.facility_name} | {vFacility.facility_type}" )
				self.currentEventPoint.captured += 1
				await self.updateParentFunction()
				return

			else: # Not new facility capture; nth call from each character.
				self.lastFacilityCaptured.participants += 1
				return

		
		
		# If reached here, facility ID doesn't match last facility ID, thus is a new capture!
		BUPrint.Debug("New Facility Capture!")
		self.lastFacilityCaptured = vNewFacilityData
		self.facilityFeed.append( f" {GetDiscordTime(vNewFacilityData.timestamp), DateFormat.TimeShorthand} | {vFacility.facility_name} | {vFacility.facility_type}" )
		self.currentEventPoint.captured += 1
		await self.updateParentFunction()

