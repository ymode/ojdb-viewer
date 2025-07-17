#!/usr/bin/env python3
"""
OJDB Viewer Layout Configuration
Simple utility to adjust layout settings
"""

# Default layout settings that can be customized
LAYOUT_CONFIG = {
    # Window settings
    'window_width': 1400,
    'window_height': 900,
    'window_title': 'OJDB Viewer (Our Jank Database Viewer)',
    
    # Splitter settings (tree_width, data_width)
    'splitter_sizes': [350, 1050],
    'tree_min_width': 250,
    'tree_max_width': 400,
    'data_min_width': 600,
    
    # Table settings
    'table_row_height': 25,
    'table_min_column_width': 80,
    'table_max_column_width': 300,
    'rows_per_page_default': 100,
    
    # UI spacing
    'main_margin': 10,
    'main_spacing': 10,
    'filter_spacing': 10,
    'pagination_spacing': 10,
    
    # Button settings
    'button_height': 30,
    'button_max_width': 100,
}

def get_config():
    """Get current layout configuration"""
    return LAYOUT_CONFIG.copy()

def set_compact_layout():
    """Configure for smaller screens"""
    LAYOUT_CONFIG.update({
        'window_width': 1200,
        'window_height': 700,
        'splitter_sizes': [300, 900],
        'tree_max_width': 350,
        'table_max_column_width': 250,
        'main_margin': 5,
        'main_spacing': 5,
    })
    return LAYOUT_CONFIG

def set_large_layout():
    """Configure for large screens"""
    LAYOUT_CONFIG.update({
        'window_width': 1600,
        'window_height': 1000,
        'splitter_sizes': [400, 1200],
        'tree_max_width': 500,
        'data_min_width': 800,
        'table_max_column_width': 400,
    })
    return LAYOUT_CONFIG

def set_wide_layout():
    """Configure for ultrawide screens"""
    LAYOUT_CONFIG.update({
        'window_width': 1800,
        'window_height': 900,
        'splitter_sizes': [450, 1350],
        'tree_max_width': 600,
        'data_min_width': 1000,
    })
    return LAYOUT_CONFIG

if __name__ == "__main__":
    print("OJDB Viewer Layout Configuration")
    print("=================================")
    print(f"Default window size: {LAYOUT_CONFIG['window_width']}x{LAYOUT_CONFIG['window_height']}")
    print(f"Tree panel width: {LAYOUT_CONFIG['splitter_sizes'][0]}")
    print(f"Data panel width: {LAYOUT_CONFIG['splitter_sizes'][1]}")
    print(f"Table row height: {LAYOUT_CONFIG['table_row_height']}")
    print()
    print("To customize layout, import this module and call:")
    print("  set_compact_layout()   # For smaller screens")
    print("  set_large_layout()     # For large screens") 
    print("  set_wide_layout()      # For ultrawide screens")
    print()
    print("Or modify LAYOUT_CONFIG dictionary directly.") 