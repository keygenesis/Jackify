{
  description = "Jackify (AppImage) packaged for NixOS with .desktop";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs {
        inherit system;
        config.allowUnfree = true;
      };
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

          cp ${srcTree}/assets/JackifyLogo_256.png \
            $out/share/icons/hicolor/256x256/apps/jackify.png

          find $out/share/applications -maxdepth 1 -name "*.desktop" -delete

          mv $out/bin/jackify $out/bin/jackify-real

          cat > $out/bin/jackify <<EOF
#!/usr/bin/env bash
set -euo pipefail

export SSL_CERT_FILE="${pkgs.cacert}/etc/ssl/certs/ca-bundle.crt"
export NIX_SSL_CERT_FILE="$SSL_CERT_FILE"
export CURL_CA_BUNDLE="$SSL_CERT_FILE"
export REQUESTS_CA_BUNDLE="$SSL_CERT_FILE"

exec ${pkgs.steam-run}/bin/steam-run "$out/bin/jackify-real" "\$@"
EOF

          chmod +x $out/bin/jackify

          cat > $out/share/applications/jackify.desktop <<EOF
[Desktop Entry]
Type=Application
Name=Jackify
Comment=Installation and configuration tool for Wabbajack modlists
Exec=$out/bin/jackify %u
Icon=jackify
Categories=Utility;
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
        };
      };
    in {
      packages.${system} = {
        jackify = jackify;
        default = jackify;
      };

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
