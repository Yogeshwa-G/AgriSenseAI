"""Tool registry for AgriSenseAI."""


class Tool:
    name = "tool"
    description = ""
    args_doc = "{}"

    def execute(self, **kwargs):
        raise NotImplementedError


def build_tools():
    from tools.calculator import Calculator
    from tools.crop_stress import CropStress
    from tools.data_query import ListFiles, ReadFile, SQLQuery
    from tools.web_search import WebSearch
    from tools.soil_analysis import SoilAnalysis
    from tools.irrigation import IrrigationAnalysis
    from tools.weather import WeatherForecast
    from tools.fertilizer import FertilizerAdvisor


    tools = [
        Calculator(),
        WebSearch(),
        CropStress(),
        ListFiles(),
        ReadFile(),
        SQLQuery(),
        SoilAnalysis(),
        IrrigationAnalysis(),
        WeatherForecast(),
        FertilizerAdvisor(),
    ]

    return {tool.name: tool for tool in tools}