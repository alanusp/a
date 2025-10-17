{
  description = "Hyperion fraud stack reproducible dev shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-23.11";

  outputs = { self, nixpkgs }: let
    system = "x86_64-linux";
    pkgs = import nixpkgs { inherit system; };
  in {
    devShells.${system}.default = pkgs.mkShell {
      buildInputs = with pkgs; [
        python311
        python311Packages.uv
        python311Packages.pip-tools
        nodejs_20
        esbuild
        open-policy-agent
        k6
        jdk17
        cosign
        sops
        age
        duckdb
        jq
      ];
    };
  };
}
