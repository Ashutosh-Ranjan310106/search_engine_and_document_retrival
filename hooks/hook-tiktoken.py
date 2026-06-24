from PyInstaller.utils.hooks import collect_data_files
datas = collect_data_files('tiktoken')
hiddenimports = ['tiktoken_ext', 'tiktoken_ext.openai_public']
