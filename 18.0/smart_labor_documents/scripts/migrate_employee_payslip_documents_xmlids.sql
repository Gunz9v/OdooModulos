BEGIN;

UPDATE ir_model_data
   SET module = 'employee_legajo_documents'
 WHERE module = 'employee_payslip_documents'
   AND (
        name IN (
            'document_type_agreement',
            'document_type_contract',
            'document_type_cv',
            'document_type_fourth_fifth_suspension',
            'document_type_payslip',
            'document_type_sanction',
            'document_type_termination',
            'document_type_tr5_high',
            'document_type_tr5_low',
            'action_employee_document_files',
            'action_employee_document_history',
            'action_employee_document_types',
            'action_prepare_all_employee_legajos',
            'model_employee_document_file',
            'model_employee_document_history',
            'model_employee_document_type',
            'model_hr_employee',
            'access_employee_document_file_hr',
            'access_employee_document_file_portal',
            'access_employee_document_file_user',
            'access_employee_document_history_hr',
            'access_employee_document_history_portal',
            'access_employee_document_history_user',
            'access_employee_document_type_hr',
            'rule_employee_document_file_employee_own',
            'rule_employee_document_file_hr_all',
            'rule_employee_document_history_employee_own',
            'rule_employee_document_history_hr_all',
            'menu_employee_document_configuration',
            'menu_employee_document_types',
            'menu_employee_documents_general_root',
            'menu_employee_legajo_history',
            'menu_employee_legajos',
            'menu_prepare_all_employee_legajos',
            'view_employee_document_file_form',
            'view_employee_document_file_list',
            'view_employee_document_file_search',
            'view_employee_document_history_form',
            'view_employee_document_history_list',
            'view_employee_document_history_search',
            'view_employee_document_type_form',
            'view_employee_document_type_list',
            'view_employee_form_legajo'
        )
        OR name LIKE 'field_employee_document_file__%'
        OR name LIKE 'field_employee_document_history__%'
        OR name LIKE 'field_employee_document_type__%'
        OR name LIKE 'field_hr_employee__legajo_%'
        OR name LIKE 'selection__employee_document_%'
        OR name LIKE 'model_inherit__employee_document_%'
   );

UPDATE ir_model_data
   SET module = 'smart_labor_documents'
 WHERE module = 'employee_payslip_documents';

COMMIT;
