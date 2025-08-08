# src/icon.py

from PyQt6.QtGui import QIcon, QPixmap
from PyQt6.QtCore import QByteArray

# 새 다운로드 아이콘 (Flaticon "Footage" 아이콘, Base64로 변환)
APP_ICON_B64 = """
data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAACXBIWXMAAAHYAAAB2AH6XKZyAAAAGXRFWHRTb2Z0d2FyZQB3d3cuaW5rc2NhcGUub3Jnm+48GgAABU1JREFUeJztmltsFFUYx39ndroXWyhpbROBKNHSpIVEvJAGqY1yixLDkyQENPrkAzEiD8aoPJgo0RAbAiKC8uItgsFEY4IBagURqqQihhaDNiRYbq6lpKWwtznz+VDbbstuO7vMTrt1f8lJZmfOnvN9/3O+b86cGShQoECBAgUK/F9Rmf6hZvmJBmXIC4LUA5XZtOEyAoQFjvgUW9q/efDHTP6cgfGiqpe1NAqyPkMDPUWExo6DD70ESpzUdyzAPY98t0HgjexN8xBRr549vOgtJ1UdCTCjbt9M0+RPIHhLhnlHxMas6jy67OJYFU1HzenoSm3njfMAIeBJYOtYFR0JYJYWNwTKplFUUgxqvHPeGIhg3YgQ7+ldggMBRvVmzuvhkqKosQORNeOf7LPikBJZ8+umirShkNarBes7Q31G6HugLiemecdF0yfz04mQNgR6dPBN0XnvPMB0K6E+ApamuphyBsx68eo0f1xfBgK5tMxLlCHzz2yraB15PuUMMCJ6kYaAYUAgCIYpEz73jUQEbEsRi4Jtg7J5AnAmQCgk86aWQUnpxE/6oyOIwPUe6O5Sc1PVuMm9JVvC9YjarxS35d5A7xBNHJ8sblpXOexZYZgAj22+NMtS5i9AmafWeYZcQZn3N60r+2vgjJF82VLmRoQyBCZnUeWi9cZknwdnwJK3u0vFr8OAPwNJ85FYNEHF0ZcrrkFSErRN615ETXbnAQLBIpkHHIEkAcSWijxP+Y4RZVQMHA/NAJThbAsh/xGxfQPH5vAL7ncWMBVPLQjRUB2gOKD4/ZLFnuMR2i4k3O/MKUkTfUgADeJyBPhNxeZVpdROH+rm4dl+6mf7aT4dY8fh64R7bXc7dYBK6nLQMo3TXTTnrJgXpOYOH5Jiai2q8bNwdhF7W6N80hIhEvcu/pIlz2kIPHCXmdL5Afw+WF0XZGmtnw9/uMGBtjieyJA004cWQrpfADfLlIByVO/2EoNXlpewdfUUqipN1+0YWdBDAuQ0BPoXYM4bnTvT5INnp3CgLc7OQxGu9OUmP6QNAbfnn4iMGgLpWDaniIZqk90/x/isJUZCu2xY2ruAu90gdnYCAARMeGZhgMW1RbzzbYST5yyXretn2MNQrmMvmzJjmkHjqmIWVrmXG5IZygHa/c0PIfsZkIwCnl8a4mjHNWwX0oKdah0A7t8GM02Co1E5FaaXGnR2u5sYkwRIvWC5FW4lB6RsTxTiwnJVqaHIz2kI2NJf3OByj3C+23ZllnoXAlneBkeibdi6P4bOwbJgwgtw/qpN474EJ8+5571KtQ7Q2v23fyKSdRKMxoXdP2k+P6aJW+6OjGcPQ9m0KQJNpzTvN1tc7cuBQeDdfoAtZBQCpzqFbfst/ric2z2ClPsBgOtr4d4bNiLGmPW6eoVdhzQHT7mT5TMhp0+DrWdt6qrSCxCz4Mvjmk+PaCJxd/seDdurEPi6VXi0VqidObxhEWhut9nZpAn3ejzkMCwL5jQJxhLCuo8tnq43aKgxKAnC6QvCnmOats5xcPw/kocjpyEAEIsLu5o1u5r12JU9ImUIKI3tdghMVAyRwdFIejGi/8EeO2NPBkQZ4YHjQQGMBCe0jyj58zFktsSsoP5t4MfgkLdvr+wTYe947wDluiDsObOp/80wjLgLGOLboNGPA+VeDIX3SJclxobkMzelveq13fWC/RWTTgTpEmWs6HivvCX5bMq8f/dz3XcaPnsjsJL8/1QuCnyBqV7reLf8/MiLo38quzZckhDuE/FViiKvbhFKsLWt/g6Z1sn27ZV9421PgQIFChSYiPwLkzSS+s+cDxUAAAAASUVORK5CYII=
"""

def get_app_icon():
    pixmap = QPixmap()
    # Base64 데이터에서 "data:image/png;base64," 접두사를 제거하고 디코딩
    base64_data = APP_ICON_B64.split(',')[1].encode() if ',' in APP_ICON_B64 else APP_ICON_B64.encode()
    pixmap.loadFromData(QByteArray.fromBase64(base64_data))
    if not pixmap.isNull():
        return QIcon(pixmap)
    else:
        # 기본 아이콘 (실패 시 임시 대체)
        pixmap = QPixmap(32, 32)
        pixmap.fill(Qt.GlobalColor.black)  # 임시 검정 사각형
        return QIcon(pixmap)
