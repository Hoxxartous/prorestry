#!/usr/bin/env python3
"""
Fix Unicode logging issues on Windows
This script removes Unicode characters from log messages to prevent encoding errors
"""

import os
import re

def fix_unicode_in_file(file_path):
    """Remove Unicode characters from a Python file"""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return False
    
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # Dictionary of Unicode characters to replace
        unicode_replacements = {
            '✅': '[OK]',
            '❌': '[ERROR]',
            '⚠️': '[WARNING]',
            '🔧': '[CONFIG]',
            '🚀': '[START]',
            '📊': '[INFO]',
            '💡': '[TIP]',
            '🎯': '[TARGET]',
            '🔍': '[SEARCH]',
            '📝': '[NOTE]',
            '🎉': '[SUCCESS]',
            '⭐': '[STAR]',
            '🔥': '[HOT]',
            '💯': '[100]',
            '🌟': '[STAR]',
            '✨': '[SPARKLE]',
        }
        
        # Replace Unicode characters
        original_content = content
        for unicode_char, replacement in unicode_replacements.items():
            content = content.replace(unicode_char, replacement)
        
        # Check if any changes were made
        if content != original_content:
            # Backup original file
            backup_path = file_path + '.backup'
            with open(backup_path, 'w', encoding='utf-8') as f:
                f.write(original_content)
            
            # Write fixed content
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            
            print(f"Fixed Unicode characters in: {file_path}")
            print(f"Backup saved as: {backup_path}")
            return True
        else:
            print(f"No Unicode characters found in: {file_path}")
            return False
            
    except Exception as e:
        print(f"Error processing {file_path}: {e}")
        return False

def fix_logging_unicode():
    """Fix Unicode logging issues in the POS system"""
    print("🔧 FIXING UNICODE LOGGING ISSUES")
    print("=" * 50)
    
    # Files to check and fix
    files_to_fix = [
        'app/__init__.py',
        'app/db_init.py',
        'app/models.py',
        'app/auth/views.py',
        'app/pos/views.py',
        'app/admin/views.py',
        'app/superuser/views.py',
        'config.py',
    ]
    
    fixed_files = []
    
    for file_path in files_to_fix:
        if fix_unicode_in_file(file_path):
            fixed_files.append(file_path)
    
    print("\n" + "=" * 50)
    print("SUMMARY")
    print("=" * 50)
    
    if fixed_files:
        print(f"Fixed {len(fixed_files)} files:")
        for file_path in fixed_files:
            print(f"  - {file_path}")
    else:
        print("No files needed Unicode fixes")
    
    print("\n💡 ADDITIONAL RECOMMENDATIONS:")
    print("1. Set environment variable: PYTHONIOENCODING=utf-8")
    print("2. Use Windows Terminal instead of Command Prompt")
    print("3. Restart your Flask application after fixes")
    
    return len(fixed_files) > 0

if __name__ == "__main__":
    print("Unicode Logging Fix for Windows")
    print("This will replace Unicode characters with ASCII equivalents")
    
    response = input("\nProceed with fixing Unicode characters? (y/n): ").lower().strip()
    
    if response in ['y', 'yes']:
        success = fix_logging_unicode()
        
        if success:
            print("\n✅ Unicode fixes applied!")
            print("Restart your Flask application to see the changes.")
        else:
            print("\n✅ No Unicode issues found.")
    else:
        print("Fix cancelled.")
