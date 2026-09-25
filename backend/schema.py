import math
import re
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import WEATHER_URL as MOCK_URL, DEVELOPER_URL, PRODUCTION, PUBLIC_ORIGIN
TARGETS = {'fill': '#tracking-id', 'click': 'button[type="submit"]', 'extract': '#tracking-result .status'}
WEATHER_INPUTS = ['#latitude-input', '#longitude-input']
WEATHER_CLICK = '#check-weather-button'
WEATHER_RESULT = '#temperature-result'

def columns_of(value):
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        return value.get('input_columns') or [value['input_column']]
    return value.input_columns

def developer(value):
    return (value.get("mode") if isinstance(value, dict) else getattr(value, "mode", None)) == "developer"

def input_bindings(value):
    columns = columns_of(value)
    return dict(zip(['#email-input', '#password-input'] if developer(value) else WEATHER_INPUTS if len(columns) == 2 else [TARGETS['fill']], columns))

def valid_coordinates(values):
    if len(values) != 2:
        return False
    return all(re.fullmatch(r'[+-]?(?:\d+(?:\.\d*)?|\.\d+)', v.strip()) and math.isfinite(float(v)) and -limit <= float(v) <= limit for v, limit in zip(values, [90, 180]))

def row_key(row, columns):
    values = [str(row[c]).strip() for c in columns_of(columns)]
    if len(values) == 2 and valid_coordinates(values):
        return tuple(float(v) for v in values)
    return tuple(v.upper() for v in values)

def valid_temperature(text):
    match = re.fullmatch(r'([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*°C', text.strip())
    return bool(match and math.isfinite(float(match[1])))

class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid')

class Mapping(StrictModel):
    mode: Literal["lookup", "developer"] = "lookup"
    expected_column: str | None = None
    status_column: str | None = None
    input_columns: list[str] = Field(default_factory=list, max_length=2)
    input_column: str | None = None  # Compatibility alias for saved one-input plans.
    destination_column: str = Field(min_length=1, max_length=100)

    @model_validator(mode='before')
    @classmethod
    def normalize_inputs(cls, value):
        if isinstance(value, dict):
            value = dict(value)
            if not value.get('input_columns') and value.get('input_column'):
                value['input_columns'] = [value['input_column']]
            if value.get('input_columns'):
                if value.get('input_column') and value['input_column'] != value['input_columns'][0]:
                    raise ValueError('Input alias must match the first input column')
                value['input_column'] = value['input_columns'][0]
        return value

    @model_validator(mode='after')
    def unique_inputs(self):
        if not self.input_columns or len(set(self.input_columns)) != len(self.input_columns) or any(not c.strip() or len(c) > 100 for c in self.input_columns):
            raise ValueError('Choose one or two distinct nonblank input columns')
        if self.destination_column in self.input_columns:
            raise ValueError('Input and destination columns must differ')
        if self.mode == 'developer':
            names = self.input_columns + [self.destination_column, self.expected_column, self.status_column]
            if len(self.input_columns) != 2 or any(not n or not n.strip() or len(n) > 100 for n in names) or len(set(names)) != 5:
                raise ValueError('Choose two inputs and distinct expected, actual and status columns')
        elif self.expected_column or self.status_column:
            raise ValueError('Assertions require developer mode')
        return self

class Step(StrictModel):
    action: Literal['fill', 'click', 'wait', 'extract', 'write_spreadsheet']
    target: str | None = None
    value: str | None = None
    save_as: str | None = None
    column: str | None = None

class Exceptions(StrictModel):
    no_result: Literal['manual_review'] = 'manual_review'

class Workflow(Mapping):
    workflow_name: str = Field(min_length=1, max_length=100)
    goal: str = Field(min_length=1, max_length=300)
    url: str = Field(default=MOCK_URL, max_length=2048)
    loop: Literal['for_each_populated_row']
    steps: list[Step] = Field(min_length=4, max_length=6)
    exceptions: Exceptions

    @model_validator(mode='after')
    def safe_plan(self):
        if PRODUCTION and not PUBLIC_ORIGIN:
            raise ValueError('Configure the production public origin before recording or execution')
        dev = developer(self)
        if self.url != (DEVELOPER_URL if dev else MOCK_URL):
            raise ValueError('Target must match the selected local mode')
        weather = len(self.input_columns) == 2
        click_target = '#login-button' if dev else WEATHER_CLICK
        result_target = '#login-result' if dev else WEATHER_RESULT
        expected = ['fill', 'fill', 'click', 'wait', 'extract', 'write_spreadsheet'] if weather else ['fill', 'click', 'extract', 'write_spreadsheet']
        if [s.action for s in self.steps] != expected:
            raise ValueError('Unexpected action sequence for the selected inputs')
        bindings = input_bindings(self)
        for index, (target, column) in enumerate(bindings.items()):
            if self.steps[index].model_dump(exclude_none=True) != {'action': 'fill', 'target': target, 'value': '{{row.' + column + '}}'}:
                raise ValueError('Each input must be bound to its own demonstrated field; fixed values are not allowed')
        click = self.steps[len(bindings)]
        if click.model_dump(exclude_none=True) != {'action': 'click', 'target': click_target if weather else TARGETS['click']}:
            raise ValueError('Only the demonstrated local button is supported')
        if weather and self.steps[3].model_dump(exclude_none=True) != {'action': 'wait', 'target': result_target}:
            raise ValueError('Wait for the current temperature result')
        variable = 'actual' if dev else 'temperature' if weather else 'status'
        if self.steps[-2].model_dump(exclude_none=True) != {'action': 'extract', 'target': result_target if weather else TARGETS['extract'], 'save_as': variable}:
            raise ValueError('Extract the demonstrated result')
        if self.steps[-1].model_dump(exclude_none=True) != {'action': 'write_spreadsheet', 'column': self.destination_column, 'value': '{{' + variable + '}}'}:
            raise ValueError('Write the extracted value to the selected output column')
        return self

class TeachRequest(Mapping):
    dataset_id: str
    row_index: int = Field(ge=0)

class Event(StrictModel):
    action: Literal['navigate', 'focus', 'fill', 'click', 'wait', 'extract']
    target: str = Field(max_length=200)
    label: str = Field(default='', max_length=150)
    role: str = Field(default='', max_length=50)
    value: str = Field(default='', max_length=500)
    text: str = Field(default='', max_length=500)
    url: str = Field(default=MOCK_URL, max_length=2048)

    @model_validator(mode='after')
    def safe_url(self):
        if (PRODUCTION and not PUBLIC_ORIGIN) or self.url not in (MOCK_URL, DEVELOPER_URL):
            raise ValueError('Only the configured bundled demo URLs are supported')
        return self

class EventBatch(StrictModel):
    events: list[Event] = Field(min_length=1, max_length=50)

class InferRequest(Mapping):
    dataset_id: str

class RunRequest(StrictModel):
    workflow_id: str
    dataset_id: str

class Resolution(StrictModel):
    value: str = Field(min_length=1, max_length=200)

def demonstrated_plan(input_column: str | list[str], destination_column: str) -> Workflow:
    columns = columns_of(input_column)
    dev = developer(input_column)
    weather = len(columns) == 2
    variable = 'actual' if dev else 'temperature' if weather else 'status'
    steps = [Step(action='fill', target=target, value='{{row.' + column + '}}') for target, column in input_bindings(input_column).items()]
    steps.append(Step(action='click', target='#login-button' if dev else WEATHER_CLICK if weather else TARGETS['click']))
    if weather:
        steps.append(Step(action='wait', target='#login-result' if dev else WEATHER_RESULT))
    steps.extend([Step(action='extract', target='#login-result' if dev else WEATHER_RESULT if weather else TARGETS['extract'], save_as=variable), Step(action='write_spreadsheet', column=destination_column, value='{{' + variable + '}}')])
    return Workflow(mode='developer' if dev else 'lookup', expected_column=getattr(input_column, 'expected_column', None), status_column=getattr(input_column, 'status_column', None), url=DEVELOPER_URL if dev else MOCK_URL, workflow_name='Learned login test' if dev else 'Check Current Weather' if weather else 'Check Tracking Status', goal='Run browser tests and compare expected results' if dev else 'Look up current temperature for each coordinate pair' if weather else 'Verify each tracking ID on the local mock website', input_columns=columns, destination_column=destination_column, loop='for_each_populated_row', steps=steps, exceptions=Exceptions())
