# Dependências distribuídas

A aplicação 2.0 usa PySide6 Essentials, Shiboken6 e bibliotecas Qt 6 carregadas dinamicamente. O build local usa a versão 6.12.0. O código dessas dependências não foi modificado. O `.spec` utiliza o estilo Basic e inclui apenas os módulos QML necessários à interface.

- [Qt for Python: licenças e atribuições](https://doc.qt.io/qtforpython-6/licenses.html)
- [Código-fonte do PySide6 e Shiboken](https://code.qt.io/cgit/pyside/pyside-setup.git/)
- [Código-fonte dos módulos Qt](https://code.qt.io/cgit/qt/)
- [Qt 6.12: distribuição dos fontes](https://download.qt.io/archive/qt/6.12/)

Os metadados dos pacotes PySide6 Essentials e Shiboken6 identificam LGPL 3.0 / GPL como opções de licença. Os textos LGPL 3.0 e GPL 3.0 acompanham o projeto em `docs/licenses/` e são copiados para a distribuição Windows. As bibliotecas Qt permanecem separadas em `_internal/PySide6`, permitindo sua substituição por versões compatíveis.

O executável também inclui o runtime Python e o bootloader do PyInstaller; seus textos de licença estão em `docs/licenses/Python-3.14.txt` e `docs/licenses/PyInstaller.txt`. O build copia essa pasta para `_internal/licenses`. O código-fonte da aplicação é entregue em um ZIP separado. Esta relação não atribui uma licença nova ao código autoral do projeto.
