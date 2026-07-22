#!/usr/bin/env emacs --script

;; Robust conversion script for Квизи.org questions to new format
;; Generates IDs from question text, not category
;; Designed for reusability and handling future conversions

(require 'org)
(require 'subr-x)

(defun quiz--slugify-text (text)
  "Create a slug from TEXT suitable for ID generation.
Converts to lowercase, trims, and replaces non-alphanumeric chars with hyphens."
  (let* ((raw (downcase (string-trim text)))
         ;; Replace whitespace/newlines with single space
         (one (replace-regexp-in-string "[[:space:]\n\r\t]+" " " raw))
         ;; Replace non-alphanumeric with hyphens
         (slug (replace-regexp-in-string "[^[:alnum:]-]" "-" one))
         ;; Remove leading/trailing hyphens
         (trimmed (replace-regexp-in-string "^-+\\|-+$" "" slug))
         ;; Collapse multiple hyphens
         (collapsed (replace-regexp-in-string "-+" "-" trimmed)))
    ;; Truncate to reasonable length for ID
    (if (> (length collapsed) 40)
        (substring collapsed 0 40)
      collapsed)))

(defun quiz--make-question-id (question-text)
  "Generate a unique ID from QUESTION-TEXT.
Uses the question text to ensure uniqueness and human-readability."
  (let ((slug (quiz--slugify-text question-text))
        ;; Use sha1 for a short, unique hash suffix
        (hash (substring (sha1 question-text) 0 8)))
    (concat slug "-" hash)))

(defun quiz--extract-answer-list ()
  "Extract the next 4 answer lines from current position.
Returns (answers checks) where answers is a list and checks is a list of booleans."
  (let (answers checks)
    (dotimes (i 4)
      (forward-line 1)
      (if (looking-at "^\\s-+-\\s-\\[\\([ X]\\)\\]\\s-\\(.*\\)$")
          (let ((checked (string= (match-string 1) "X"))
                (answer-text (string-trim (match-string 2))))
            (push answer-text answers)
            (push checked checks))
        ;; If answer format is wrong, still advance but mark as invalid
        (push "" answers)
        (push nil checks)))
    (list (nreverse answers) (nreverse checks))))

(defun quiz-convert-to-new-format ()
  "Convert all quiz questions from list format to property-drawer format.
Reads from Квизи.org, outputs to Квизи-converted.org.
IDs are generated from question text for uniqueness and reusability."
  (interactive)
  (let ((input-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи.org")
        (output-file "/home/eugene/src/lewwadoo/org/org-roam/Квизи/Квизи-converted.org")
        (questions '())
        (current-category nil)
        (count 0)
        (skipped 0))
    
    (unless (file-exists-p input-file)
      (error "Input file not found: %s" input-file))
    
    (with-temp-buffer
      (insert-file-contents input-file)
      (goto-char (point-min))
      
      ;; Parse the file for questions
      ;; Structure: *** Category header
      ;;            - [ ] Question text
      ;;              - [ ] Answer 1
      ;;              - [ ] Answer 2
      ;;              - [X] Correct answer
      ;;              - [ ] Answer 4
      
      (while (re-search-forward "^\\*\\*\\*\\s-\\(.*\\)$" nil t)
        (setq current-category (string-trim (match-string 1)))
        
        ;; Look for questions in this category (lines starting with "- ")
        (let ((cat-start (point))
              (cat-end (save-excursion
                         (if (re-search-forward "^\\*\\*\\*\\s-" nil t)
                             (match-beginning 0)
                           (point-max)))))
          
          (while (re-search-forward "^- \\[.*\\]\\s-\\(.*\\)$" cat-end t)
            (let ((question-text (string-trim (match-string 1))))
              ;; Extract the 4 answers
              (let* ((result (quiz--extract-answer-list))
                     (answers (car result))
                     (checks (cadr result))
                     ;; Find the index of the correct answer (1-based)
                     (correct-idx (or (+ 1 (cl-position t checks))
                                      nil)))
                
                ;; Validate: must have exactly 4 answers and exactly 1 checked
                (if (and (= (length answers) 4)
                         (= (cl-count t checks) 1)
                         correct-idx)
                    (progn
                      (push (list :category current-category
                                  :question question-text
                                  :answers answers
                                  :correct correct-idx)
                            questions)
                      (setq count (1+ count)))
                  (progn
                    (message "WARNING: Skipping malformed question in category '%s': %s"
                             current-category question-text)
                    (setq skipped (1+ skipped))))))))))
    
    ;; Generate output file
    (with-temp-file output-file
      ;; Header
      (insert ":PROPERTIES:\n")
      (insert ":ID:       26ad5ae6-8e94-4de3-a0b6-88e02266d639\n")
      (insert ":END:\n")
      (insert "#+title: Квизи (Converted)\n\n")
      (insert "* Вопросы\n")
      (insert ":PROPERTIES:\n")
      (insert ":ID:       fb8e6949-be87-49a9-b252-c98f4a3deb35\n")
      (insert ":END:\n")
      (insert "** Категории\n\n")
      
      ;; Group questions by category and output
      (let ((categories (make-hash-table :test 'equal)))
        ;; Group questions by category
        (dolist (q (nreverse questions))
          (let ((cat (plist-get q :category)))
            (puthash cat (cons q (gethash cat categories '())) categories)))
        
        ;; Output each category with its questions
        (maphash (lambda (cat-name cat-questions)
                   (insert (format "*** %s\n\n" cat-name))
                   (dolist (q cat-questions)
                     (let ((question (plist-get q :question))
                           (answers (plist-get q :answers))
                           (correct (plist-get q :correct))
                           (id (quiz--make-question-id (plist-get q :question))))
                       (insert (format "**** %s\n" question))
                       (insert ":PROPERTIES:\n")
                       (insert (format ":ID:       %s\n" id))
                       (insert (format ":CORRECT:   %d\n" correct))
                       (dotimes (i 4)
                         (insert (format ":ANSWER%d:   %s\n" (1+ i) (nth i answers))))
                       (insert ":END:\n\n"))))
                 categories)))
    
    ;; Report results
    (message "✓ Conversion completed successfully!")
    (message "  Total questions converted: %d" count)
    (message "  Skipped (malformed): %d" skipped)
    (message "  Output saved to: %s" output-file)))

;; Run the conversion
(quiz-convert-to-new-format)
