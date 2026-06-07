Guia rápido para publicar os installers no GitHub

1) Subir os installers locais (mais simples)

- Instale e autentique o GitHub CLI (`gh`):

  ```bash
  # Debian/Ubuntu
  sudo apt install gh
  gh auth login
  ```

- Execute o script para criar a release e enviar os assets:

  ```bash
  chmod +x scripts/upload_release.sh
  ./scripts/upload_release.sh v1.0.0 "Elyra Installer 1.0.0" dist/Elyra-Installer-x86_64.AppImage dist/elyra-installer_1.0.0_amd64.deb "build/Elyra Installer/Elyra Installer.pkg"
  ```

  - Substitua `v1.0.0` e o nome pelo tag/nome que desejar.
  - O comando assume que os arquivos estão em `dist/` e `build/` como no repositório atual.

2) Publicar automaticamente via GitHub Actions (opcional)

- Há um workflow em `.github/workflows/upload-release-assets.yml` que, quando uma *release* for publicada, tentará anexar os arquivos presentes em `dist/` e `build/Elyra Installer/` ao release.

- Observação importante: o runner só tem acesso aos arquivos que estão no repositório ou gerados no próprio workflow. Se você quiser que o workflow construa os installers automaticamente, podemos estender o workflow para executar os scripts de build antes do upload.

3) Comitar e subir os scripts/instruções

Se quiser que eu também faça o commit e o push dessas mudanças para o seu repositório remoto, confirme o remote e eu posso executar os comandos Git localmente (é necessário que o ambiente tenha acesso ao remoto e que você concorde).
