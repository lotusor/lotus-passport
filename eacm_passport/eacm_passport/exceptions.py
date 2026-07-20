"""
自定义异常处理
"""
from rest_framework.views import exception_handler
from rest_framework.response import Response
from rest_framework import status


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)
    if response is not None:
        custom_data = {
            'code': response.status_code,
            'message': _extract_message(response),
            'data': response.data if isinstance(response.data, (list, dict)) else None
        }
        # 对手机号冲突等场景提供友好提示
        if response.status_code == 409:
            custom_data['message'] = '该手机号已被其他账户绑定，请确认是否合并账户'
            custom_data['conflict'] = True
        response.data = custom_data
    return response


def _extract_message(response):
    """从DRF错误响应中提取可读消息"""
    data = response.data
    if isinstance(data, dict):
        # 取第一个错误字段的消息
        for key, value in data.items():
            if isinstance(value, list) and value:
                return f"{key}: {value[0]}"
            if isinstance(value, str):
                return f"{key}: {value}"
        return data.get('detail', '请求错误')
    if isinstance(data, list):
        return data[0] if data else '请求错误'
    if isinstance(data, str):
        return data
    return '请求错误'