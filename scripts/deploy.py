def package_function():
    """Package the function code for deployment"""
    print("\nPackaging function code...")
    
    # Create temp directory if it doesn't exist
    os.makedirs('temp', exist_ok=True)
    
    # Create package structure
    print("\nCreating package structure...")
    os.makedirs('temp/services', exist_ok=True)
    os.makedirs('temp/models', exist_ok=True)
    os.makedirs('temp/utils', exist_ok=True)
    os.makedirs('temp/scripts', exist_ok=True)  # For setup scripts
    os.makedirs('temp/terraform', exist_ok=True)  # For Terraform files
    os.makedirs('temp/tests', exist_ok=True)  # For test files
    
    # Copy Python files
    print("\nCopying Python files...")
    files_copied = []
    total_size = 0
    
    # Copy main function file
    shutil.copy2('main.py', 'temp/main.py')
    files_copied.append(('main.py', 'main.py'))
    total_size += os.path.getsize('main.py')
    
    # Copy src directory structure without the src prefix
    for root, _, files in os.walk('src'):
        for file in files:
            if file.endswith('.py'):
                src_path = os.path.join(root, file)
                # Remove 'src' from the path
                rel_path = os.path.relpath(src_path, 'src')
                dst_path = os.path.join('temp', rel_path)
                os.makedirs(os.path.dirname(dst_path), exist_ok=True)
                shutil.copy2(src_path, dst_path)
                files_copied.append((src_path, rel_path))
                total_size += os.path.getsize(src_path)
    
    # Copy setup and deployment files
    setup_files = [
        ('scripts/setup.bat', 'scripts/setup.bat'),
        ('scripts/setup.sh', 'scripts/setup.sh'),
        ('scripts/deploy.py', 'scripts/deploy.py'),
        ('scripts/test_deployment.py', 'scripts/test_deployment.py'),
        ('scripts/test_function.py', 'scripts/test_function.py'),
        ('scripts/test_deployment_package.py', 'scripts/test_deployment_package.py'),
        ('scripts/setup_oauth.py', 'scripts/setup_oauth.py'),
        ('scripts/setup_credentials.py', 'scripts/setup_credentials.py'),
        ('scripts/setup_service_accounts.py', 'scripts/setup_service_accounts.py'),
        ('scripts/deploy_credentials.py', 'scripts/deploy_credentials.py'),
        ('scripts/deploy_functions.py', 'scripts/deploy_functions.py'),
        ('scripts/deploy_scheduler.py', 'scripts/deploy_scheduler.py'),
        ('scripts/deploy_storage.py', 'scripts/deploy_storage.py')
    ]
    
    # Copy test files
    test_files = [
        ('tests/test_gmail_integration.py', 'tests/test_gmail_integration.py'),
        ('tests/test_transaction_parse.py', 'tests/test_transaction_parse.py'),
        ('tests/test_email_api_id.py', 'tests/test_email_api_id.py')
    ]
    
    # Copy Terraform files
    terraform_files = []
    for root, _, files in os.walk('terraform'):
        for file in files:
            src_path = os.path.join(root, file)
            rel_path = os.path.relpath(src_path)
            terraform_files.append((src_path, rel_path))
    
    # Copy configuration files
    print("\nCopying configuration files...")
    config_files = [
        ('requirements.txt', 'requirements.txt'),
        ('config.yaml', 'config.yaml'),
        ('config.yaml.example', 'config.yaml.example'),
        ('cloudbuild.yaml', 'cloudbuild.yaml'),
        ('app.yaml', 'app.yaml'),
        ('Dockerfile', 'Dockerfile'),
        ('.env.example', '.env.example'),
        ('SETUP.md', 'SETUP.md'),
        ('README.md', 'README.md'),
        ('ARCHITECTURE.md', 'ARCHITECTURE.md'),
        ('CREDENTIAL_MANAGEMENT.md', 'CREDENTIAL_MANAGEMENT.md')
    ]
    
    # Copy all files
    all_files = setup_files + test_files + terraform_files + config_files
    config_size = 0
    
    for src, dst in all_files:
        if os.path.exists(src):
            dst_path = os.path.join('temp', dst)
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            shutil.copy2(src, dst_path)
            size = os.path.getsize(src)
            config_size += size
            print(f"✓ Copied {src} to {dst} ({format_size(size)})")
    
    print(f"Total config size: {format_size(config_size)}")
    
    # Create zip file
    print("\nCreating zip file at temp/function.zip")
    zip_path = 'temp/function.zip'
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        for root, _, files in os.walk('temp'):
            if root == 'temp':
                files_to_zip = [f for f in files if f != 'function.zip']
            else:
                files_to_zip = files
            
            for file in files_to_zip:
                file_path = os.path.join(root, file)
                arcname = os.path.relpath(file_path, 'temp')
                zipf.write(file_path, arcname)
                print(f"✓ Added {arcname} to zip ({format_size(os.path.getsize(file_path))})")
    
    # Print package summary
    zip_size = os.path.getsize(zip_path)
    total_size = total_size + config_size
    compression_ratio = (1 - (zip_size / total_size)) * 100
    
    print("\nPackage Summary:")
    print(f"Total files: {len(files_copied) + len(all_files)}")
    print(f"Python code size: {format_size(total_size)}")
    print(f"Config files size: {format_size(config_size)}")
    print(f"Total uncompressed: {format_size(total_size)}")
    print(f"Final zip size: {format_size(zip_size)}")
    print(f"Compression ratio: {compression_ratio:.1f}%")
    
    print("\n✓ Function packaging completed") 