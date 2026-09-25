import asyncio
from backend import storage
from backend.inference import infer
from backend.schema import Mapping
async def main():
    demo = next(d for d in storage.listing('demo') if d.get('mode') == 'developer' and d['state'] == 'complete')
    mapping = Mapping(**{k: demo[k] for k in ['mode', 'input_columns', 'destination_column', 'expected_column', 'status_column']})
    plan, _ = await infer([demo], mapping, mapping.destination_column, demo['dataset_id'])
    print('Live Nemotron developer workflow validated:', plan.mode)
asyncio.run(main())
