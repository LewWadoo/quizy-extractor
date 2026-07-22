;;; quiz-widget.el --- Convert org-mode quiz entries to Emacs widgets -*- lexical-binding: t -*-

(require 'widget)
(require 'cl-lib)

(defun quiz-widget-parse-questions (org-content)
  "Parse quiz questions from ORG-CONTENT string."
  (let ((questions '())
        (current-category nil)
        (lines (split-string org-content "\n")))
    (dolist (line lines)
      (cond
       ;; Match category headers like "*** Вокруг света [0/17]"
       ((string-match "^\\*\\*\\* \\(.*?\\) \\[\\([0-9]+\\)/\\([0-9]+\\)\\]" line)
        (setq current-category (match-string 1 line)))
       
       ;; Match questions like "- [ ] Как называется индийский праздник весны..."
       ((and current-category 
             (string-match "^- \\[.\\] \\(.*\\)" line))
        (let ((question-text (match-string 1 line))
              (options '())
              (correct-answer nil))
          ;; Look ahead for options - get current index
          (let ((current-line-idx (- (length lines) (length (member line lines)))))
            (let ((next-idx (1+ current-line-idx)))
              (while (and (< next-idx (length lines))
                           (nth next-idx lines)
                           (string-match "^[ \t]*- \\[\\(\\[X?\\]\\)\\] \\(.*\\)" (nth next-idx lines)))
                  (let* ((option-line (nth next-idx lines))
                         (is-correct (string= "[X]" (match-string 1 option-line)))
                         (option-text (match-string 2 option-line)))
                    (push (list option-text is-correct) options)
                    (when is-correct
                      (setq correct-answer (length options)))
                    (setq next-idx (1+ next-idx))))))
            (when options
              (setq options (nreverse options))
              (push (list current-category question-text options correct-answer) questions)))))))
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
        (let* ((org-file-path "/home/eugene/src/lewwadoo/org-roam/квизи.org")
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

(provide 'quiz-widget)