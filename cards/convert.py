import os
import json
import urllib.parse
from lzstring import LZString


def decompress_data(compressed_data: str) -> dict:
    # 使用 LZString 解压数据
    lz = LZString()
    
    # 先进行 URL 解码
    decoded_data = urllib.parse.unquote(compressed_data)
    print(f'URL 解码后的数据: {decoded_data}')  # 打印解码后的数据
    
    # 使用 LZString 解压数据
    decompressed = lz.decompressFromEncodedURIComponent(decoded_data)
    print(f'解压后的数据: {decompressed}')  # 打印解压后的数据
    
    # 检查解压后的数据是否为空或无效
    if not decompressed or decompressed.strip() == "":
        raise ValueError("解压后的数据为空或无效，无法解析为 JSON。")
    
    # 将解压后的数据解析为 JSON
    try:
        return json.loads(decompressed)
    except json.JSONDecodeError as e:
        raise ValueError(f"解压后的数据不是有效的 JSON: {e}")

def save_to_json(data: dict, filename: str) -> None:
    # 将数据保存到 JSON 文件
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f'成功解压并保存到 {filename}')

def process_files_in_directory(directory: str) -> None:
    # 遍历目录中的所有文件
    for filename in os.listdir(directory):
        if filename.endswith('.txt'):  # 只处理文本文件
            file_path = os.path.join(directory, filename)
            print(f'处理文件: {file_path}')
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    compressed_data = f.read()
                    print(f'原始文件内容: {compressed_data}')  # 打印原始内容
                    # 解压数据
                    data = decompress_data(compressed_data)
                    # 生成输出文件名
                    output_filename = os.path.splitext(filename)[0] + '.json'
                    output_path = os.path.join(directory, output_filename)
                    # 保存到 JSON 文件
                    save_to_json(data, output_path)
            except Exception as e:
                print(f'处理文件 {filename} 时发生错误: {str(e)}')

if __name__ == '__main__':
    directory = './cards'  # 使用相对路径
    process_files_in_directory(directory)