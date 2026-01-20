{
  description = "Jackify (AppImage) for NixOS";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; config.allowUnfree = true; };
      lib = pkgs.lib;

      version = "0.2.1.1";
      appImageName = "Jackify.AppImage";

      appImage = pkgs.fetchurl {
        url = "https://github.com/Omni-guides/Jackify/releases/download/v${version}/${appImageName}";
        hash = "sha256-zVreomYaYfOU6pEUlZz+rVMjeuTZBKzylUMF1ComEdQ=";
      };

      srcTree = builtins.path { path = self; name = "jackify-src"; };

      jackify = pkgs.appimageTools.wrapType2 {
        pname = "jackify";
        inherit version;
        src = appImage;

        extraPkgs = pkgs': with pkgs'; [
          (python3.withPackages (ps: with ps; [
            pyside6
            psutil
            requests
            tqdm
            pycryptodome
            pyyaml
            vdf
            packaging
          ]))

          steam-run
          cacert

          xdg-utils
          desktop-file-utils
          libnotify

          winetricks
          cabextract
          p7zip
          unzip
          gnutar
          wget
          curl
          aria2

          libGL
          xcb-util-cursor
          zstd
          zlib
          glib
          openssl
          xorg.libX11
          xorg.libXext
          xorg.libXrender
          xorg.libXrandr
          xorg.libxcb
          libxkbcommon
          fontconfig
          freetype
          gtk3
          nss
          nspr
          fuse3
        ];

        extraInstallCommands = ''
          mkdir -p \
            $out/share/applications \
            $out/share/icons/hicolor/256x256/apps

          if [ -f "${srcTree}/assets/JackifyLogo_256.png" ]; then
            cp ${srcTree}/assets/JackifyLogo_256.png \
              $out/share/icons/hicolor/256x256/apps/jackify.png
          fi

          find $out/share/applications -maxdepth 1 -name "*.desktop" -delete

          mv $out/bin/jackify $out/bin/jackify-real

          cat > $out/bin/jackify-wine <<'EOF'
#!/usr/bin/env sh
set -eu

steam_root="${HOME}/.local/share/Steam"
ctd="${steam_root}/compatibilitytools.d"

pick=""
if [ -x "${ctd}/Proton-GE Latest/files/bin/wine" ]; then
  pick="${ctd}/Proton-GE Latest/files/bin/wine"
else
  pick="$(ls -1d "${ctd}"/GE-Proton* 2>/dev/null | sort -V | tail -n 1)/files/bin/wine" || true
fi

if [ -z "${pick}" ] || [ ! -x "${pick}" ]; then
  echo "Jackify: GE-Proton wine not found in ${ctd}" >&2
  exit 1
fi

exec steam-run "${pick}" "$@"
EOF
          chmod +x $out/bin/jackify-wine

          cat > $out/bin/jackify <<EOF
#!/usr/bin/env bash
set -euo pipefail

export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
export NIX_SSL_CERT_FILE="\$SSL_CERT_FILE"
export CURL_CA_BUNDLE="\$SSL_CERT_FILE"
export REQUESTS_CA_BUNDLE="\$SSL_CERT_FILE"

export WINE="$out/bin/jackify-wine"
export WINE64="$out/bin/jackify-wine"

export PATH="${lib.makeBinPath [
  pkgs.xdg-utils
  pkgs.desktop-file-utils
  pkgs.libnotify
  pkgs.winetricks
  pkgs.cabextract
  pkgs.p7zip
  pkgs.unzip
  pkgs.gnutar
  pkgs.wget
  pkgs.curl
  pkgs.aria2
]}:\$PATH"

exec ${pkgs.steam-run}/bin/steam-run "$out/bin/jackify-real" "\$@"
EOF
          chmod +x $out/bin/jackify

          cat > $out/share/applications/jackify.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Jackify
Comment=Installation and configuration tool for Wabbajack modlists
Exec=$out/bin/jackify %U
Icon=jackify
Categories=Utility;Game;
Terminal=false
StartupNotify=true
MimeType=x-scheme-handler/jackify;
EOF
        '';

        meta = with lib; {
          description = "A modlist installation and configuration tool for Wabbajack modlists on Linux";
          homepage = "https://github.com/Omni-guides/Jackify";
          license = licenses.gpl3Only;
          platforms = [ "x86_64-linux" ];
          mainProgram = "jackify";
        };
      };
    in
    {
      packages.${system}.jackify = jackify;
      packages.${system}.default = jackify;

      apps.${system}.default = {
        type = "app";
        program = "${jackify}/bin/jackify";
      };

      overlays.default = final: prev: {
        jackify = jackify;
      };

      nixosModules.default = { pkgs, ... }: {
        nixpkgs.overlays = [ self.overlays.default ];
        environment.systemPackages = [ pkgs.jackify ];
      };
    };
}
