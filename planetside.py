import asyncio
import auraxium
from auraxium import ps2

loop = asyncio.get_event_loop()

async def main():
    # NOTE: Depending on player activity, this script will likely exceed the
    # ~6 requests per minute and IP address limit for the default service ID.
    client = auraxium.EventClient(service_id='s:example')

    @client.trigger(auraxium.EventType.BATTLE_RANK_UP)
    async def print_levelup(event):
        char_id = int(event.payload['character_id'])
        char = await client.get_by_id(ps2.Character, char_id)

        # NOTE: This value is likely different from char.data.battle_rank as
        # the REST API tends to lag by a few minutes.
        new_battle_rank = int(event.payload['battle_rank'])

        print(f'{await char.name_long()} has reached BR {new_battle_rank}!')

loop.create_task(main())
loop.run_forever()