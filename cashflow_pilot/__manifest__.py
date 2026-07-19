{
    'name': 'CashFlow Pilot',
    'summary': '13-Week Cash Flow Forecast & Liquidity Planner',
    'description': """
CashFlow Pilot
===============
A zero-configuration, rolling cash flow forecast built automatically from
data already in Odoo - bank/cash balances, open customer invoices, open
vendor bills - plus user-maintained recurring and one-off cash items.

Strictly read-only toward accounting: never creates, modifies, or deletes
journal entries, invoices, bills, or reconciliations.
""",
    'version': '19.0.1.0.0',
    'category': 'Accounting',
    'author': 'NovaERP Labs',
    'license': 'LGPL-3',
    'support': 'novaerp.labs@gmail.com',
    'depends': ['account', 'mail', 'web'],
    'data': [
        'security/security.xml',
        'security/nova_record_rules.xml',
        'security/ir.model.access.csv',
        'data/nova_category_data.xml',
        'data/nova_cron_data.xml',
        'data/nova_activity_data.xml',
        'data/nova_mail_template_data.xml',
        'data/nova_readiness_cron_data.xml',
        'views/cashflow_menus.xml',
        'views/nova_category_views.xml',
        'views/nova_move_info_views.xml',
        'views/account_move_views.xml',
        'wizard/nova_recurring_revise_wizard_views.xml',
        'views/nova_recurring_item_views.xml',
        'views/nova_manual_item_views.xml',
        'views/res_config_settings_views.xml',
        'views/nova_forecast_line_views.xml',
        'views/nova_period_report_views.xml',
        'views/nova_readiness_issue_views.xml',
        'wizard/nova_onboarding_wizard_views.xml',
        'views/nova_cockpit_views.xml',
        'report/nova_forecast_report_templates.xml',
        'report/nova_forecast_report_views.xml',
        'views/nova_export_actions.xml',
        'wizard/nova_bulk_reschedule_wizard_views.xml',
    ],
    'demo': [
        'demo/nova_demo_data.xml',
    ],
    'assets': {
        'web.assets_backend': [
            'cashflow_pilot/static/src/cockpit/**/*',
        ],
    },
    'images': ['static/description/banner.png'],
    'application': True,
    'installable': True,
    'auto_install': False,
}
