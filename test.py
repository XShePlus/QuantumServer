import json

# test_dict = {'one': 1, 'two': {2.1: ['a', 'b']}}
# json_str = json.dumps(test_dict)  # 关键操作
#
# print(f"原始类型: {type(test_dict)}")  # <class 'dict'>
# print(f"转换后类型: {type(json_str)}")  # <class 'str'>
# print(f"JSON字符串: {json_str}")      # {"one": 1, "two": {"2.1": ["a", "b"]}}
a = json.load(open("./a.json", "r"))
print(list(a))
