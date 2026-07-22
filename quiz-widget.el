;;; quiz-widget.el --- Convert org-mode quiz entries to Emacs widgets -*- lexical-binding: t -*-

;;; Commentary:
;; This file provides functionality to convert quiz questions from org-mode entries
;; to interactive Emacs widgets using radio buttons instead of checkboxes.

;;; Code:

(require 'widget)
(require 'cl-lib)

(defun quiz-widget-parse-questions (org-content)
  "Parse quiz questions from ORG-CONTENT string."
  (let ((questions '())
        (current-category nil)
        (lines (split-string org-content "\n"))
        (i 0))
    (while (< i (length lines))
      (let ((line (nth i lines)))
        (cond
         ;; Match category headers
         ((string-match "^\\*\\*\\* \\(.*?\\) \\[\\([0-9]+\\)/\\([0-9]+\\)\\]" line)
          (setq current-category (match-string 1 line))
          (setq i (1+ i)))
         
         ;; Match questions
         ((and current-category 
               (string-match "^- \\[.\\] \\(.*\\)" line))
          (let ((question-text (match-string 1 line))
                (options '())
                (correct-answer nil))
            
            ;; Collect options
            (let ((j (1+ i)))
              (while (and (< j (length lines))
                          (nth j lines)
                          (let ((option-line (nth j lines)))
                            (or (string-match "^[ \t]*- \\[X\\] \\(.*\\)" option-line)
                                (string-match "^[ \t]*- \\[ \\] \\(.*\\)" option-line))))
                
                (let* ((option-line (nth j lines))
                       (is-correct (string-match "^[ \t]*- \\[X\\] \\(.*\\)" option-line))
                       (option-text (if is-correct
                                        (match-string 1 option-line)
                                      (match-string 1 (nth j lines)))))
                  (push (list option-text is-correct) options)
                  (when is-correct
                    (setq correct-answer (length options)))
                  (setq j (1+ j))))
              
              ;; If we found options, add the question
              (when options
                (setq options (nreverse options))
                (push (list current-category question-text options correct-answer) questions)))
          
          ;; Set i to continue after options
          (setq i j))))
         
         (t
          (setq i (1+ i))))))
    
    (nreverse questions)))

(defun quiz-widget-create-question-widget (question-data)
  "Create a widget for a single QUESTION-DATA."
  (let* ((category (car question-data))
         (question-text (cadr question-data))
         (options (caddr question-data))
         (correct-answer (cadddr question-data))
         (widget-variable (gensym "quiz-answer-")))
    
    ;; Create category header
    (widget-insert (propertize (format "\n=== %s ===\n" category) 'face 'bold))
    
    ;; Create question
    (widget-insert (format "\n%s\n" question-text))
    
    ;; Create radio button options
    (cl-loop for (option-text is-correct) in options
             for i from 1
             do (widget-create 'radio-button-item
                                :value (eq i correct-answer)
                                :notify (lambda (widget &rest _)
                                          (set widget-variable i))
                                option-text)
             (widget-insert "\n"))
    
    ;; Create check answer button
    (widget-create 'push-button
                   :notify (lambda (widget &rest _)
                             (let ((user-answer (symbol-value widget-variable)))
                               (if (eq user-answer correct-answer)
                                   (message "Правильно!")
                                 (message "Неправильно. Правильный ответ: %s" 
                                          (car (nth (1- correct-answer) options))))))
                   "Проверить ответ")
    (widget-insert "\n")
    
    widget-variable))

(defun quiz-widget-display ()
  "Display the quiz widget interface."
  (interactive)
  (let ((buffer (get-buffer-create "*Quiz Widget*")))
    (with-current-buffer buffer
      (kill-all-local-variables)
      (widget-mode 1)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (widget-insert "=== Викторина ===\n")
        (widget-insert "Выберите правильный ответ и нажмите 'Проверить ответ'\n\n")
        
        ;; Parse and display questions
        (let* ((org-file-path "/home/eugene/src/lewwadoo/org/org-roam/квизи.org")
               (org-content (when (file-exists-p org-file-path)
                             (with-temp-buffer
                               (insert-file-contents org-file-path)
                               (buffer-string))))
               (questions (when org-content (quiz-widget-parse-questions org-content))))
          
          (if questions
              (dolist (question-data questions)
                (quiz-widget-create-question-widget question-data))
            (widget-insert "Не удалось загрузить вопросы из файла квизи.org\n")))))
    
    (switch-to-buffer buffer)))

(defun quiz-widget-simple-test ()
  "Simple test function."
  (interactive)
  (let ((buffer (get-buffer-create "*Quiz Test*")))
    (with-current-buffer buffer
      (kill-all-local-variables)
      (widget-mode 1)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (widget-insert "=== Test Quiz ===\n")
        (widget-insert "Как называется индийский праздник весны?\n")
        
        ;; Create radio buttons
        (widget-create 'radio-button-item :value nil "Холи")
        (widget-insert "\n")
        (widget-create 'radio-button-item :value nil "Ганеша-чатуртхи")
        (widget-insert "\n")
        (widget-create 'radio-button-item :value nil "Болливуд")
        (widget-insert "\n")
        
        ;; Check button
        (widget-create 'push-button
                       :notify (lambda (widget &rest _)
                                 (message "Answer checked!"))
                       "Проверить ответ")))
    (switch-to-buffer buffer)))

;;;###autoload
(defun quiz-widget-from-region (start end)
  "Convert quiz questions from region START to END into widgets."
  (interactive "r")
  (let ((region-content (buffer-substring-no-properties start end))
        (buffer (get-buffer-create "*Region Quiz*")))
    (with-current-buffer buffer
      (kill-all-local-variables)
      (widget-mode 1)
      (let ((inhibit-read-only t))
        (erase-buffer)
        (widget-insert "=== Викторина из выделенной области ===\n\n")
        
        (let ((questions (quiz-widget-parse-questions region-content)))
          (if questions
              (dolist (question-data questions)
                (quiz-widget-create-question-widget question-data))
            (widget-insert "Не найдено вопросов в выделенной области\n")))))
    
    (switch-to-buffer buffer)))

(provide 'quiz-widget)
;;; quiz-widget.el ends here