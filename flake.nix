{
  description = "Jackify (AppImage) packaged for NixOS with .desktop";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { self, nixpkgs }:
    let
      system = "x86_64-linux";
      pkgs = import nixpkgs { inherit system; };
      lib = pkgs.lib;

      # This version and hash must be updated for each new release
      version = "0.2.1.1";

      # AppImage asset name as published upstream
      appImageName = "Jackify.AppImage";

      appImage = pkgs.fetchurl {
        url = "https://github.com/Omni-guides/Jackify/releases/download/v${version}/${appImageName}";
        # Must be updated when the AppImage changes
        hash = "sha256-zVreomYaYfOU6pEUlZz+rVMjeuTZBKzylUMF1ComEdQ=";
      };

      # Ensure flake source is a store path for install commands
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
        # Remove the AppImage-provided desktop file (it points at extracted __main__.py)
        rm -f $out/share/applications/com.jackify.app.desktop
  
        # Ensure the remaining desktop entry launches the wrapped binary
        if [ -f $out/share/applications/jackify.desktop ]; then
          sed -i "s|^Exec=.*|Exec=$out/bin/jackify %U|g" \
            $out/share/applications/jackify.desktop
        fi
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
