pkgname=readleaf
pkgver=1.0.0
pkgrel=1
pkgdesc='A lightweight GTK 4 RTF document reader'
arch=('any')
url='https://github.com/'
license=('MIT')
depends=('gtk4' 'python' 'python-gobject')
source=('readleaf.py'
        'rtf_parser.py'
        'io.github.readleaf.Reader.desktop'
        'io.github.readleaf.Reader.svg'
        'io.github.readleaf.Reader.metainfo.xml'
        'LICENSE')
sha256sums=('20c56e928e2e373d47229089aacf492e4d03b481dbda7b45c88f69331ebd8dc5'
            'f237e1591bc141b09becca569f3d55a9f2ed066f873d280cdccf38cc6e8f29e6'
            'e4f8f078cba4dbc899bf4f6cf135e163523346211e0c48e10736a9a4ac3417e1'
            '2424fe0423e71ee5cae0f44a389e54179ef7a13d9e0c31073da158dc8d05ce24'
            '5d97a6c65ddbd5217adc6c163702755377d969497e6b0a2f0d11294f59fa2fb9'
            'c50158c329657ff0df341822ccfe51f00b473f7a08a8aa618904feed528b3e6d')

package() {
  install -Dm755 "$srcdir/readleaf.py" "$pkgdir/usr/lib/readleaf/readleaf.py"
  install -Dm644 "$srcdir/rtf_parser.py" "$pkgdir/usr/lib/readleaf/rtf_parser.py"
  install -Dm644 "$srcdir/io.github.readleaf.Reader.desktop" \
    "$pkgdir/usr/share/applications/io.github.readleaf.Reader.desktop"
  install -Dm644 "$srcdir/io.github.readleaf.Reader.svg" \
    "$pkgdir/usr/share/icons/hicolor/scalable/apps/io.github.readleaf.Reader.svg"
  install -Dm644 "$srcdir/io.github.readleaf.Reader.metainfo.xml" \
    "$pkgdir/usr/share/metainfo/io.github.readleaf.Reader.metainfo.xml"
  install -Dm644 "$srcdir/LICENSE" "$pkgdir/usr/share/licenses/$pkgname/LICENSE"
  install -d "$pkgdir/usr/bin"
  ln -s /usr/lib/readleaf/readleaf.py "$pkgdir/usr/bin/readleaf"
}
